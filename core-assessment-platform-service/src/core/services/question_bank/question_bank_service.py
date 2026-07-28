"""Question bank persistence and draft generation."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from dataclasses import dataclass
from io import StringIO
from typing import TypeVar
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config.settings import get_settings
from constants.question_tag_taxonomy import (
    normalize_question_category,
    normalize_question_tags,
)
from control.agents.question_generation_graph import QuestionGenerationWorkflow
from core.exceptions.assessment import ExecutionAdapterError
from core.exceptions.question_bank import (
    QuestionBankStoreUnavailableError,
    QuestionBankValidationError,
    QuestionGuardrailError,
    QuestionNotFoundError,
)
from core.services.execution.ports import build_execution_port
from core.services.question_bank.guardrails import (
    check_code_sast,
    check_input_guardrails,
)
from core.services.question_bank.output_validation import (
    apply_answer_validation,
    default_checker_explanation,
    normalize_answer_validation_mode,
    validate_output_checker_source,
)
from data.models.postgres.core.question_bank_question import QuestionBankQuestionModel
from data.models.postgres.core.question_group import QuestionGroupModel
from data.repositories.question_bank.question_bank_repository import (
    QuestionBankRepository,
)
from handlers.http_clients.ai_gateway import AIGatewayService
from schemas.question_bank import (
    AnswerValidationMode,
    DifficultyLevel,
    DifficultySource,
    MetadataStatus,
    QuestionAIDraftContext,
    QuestionAIDraftRequest,
    QuestionAIDraftResponse,
    QuestionBulkImportRequest,
    QuestionBulkImportResponse,
    QuestionBulkImportRowError,
    QuestionCreateRequest,
    QuestionCreationMode,
    QuestionDraftRefinementRequest,
    QuestionDraftRefinementResponse,
    QuestionDraftValidationRequest,
    QuestionDraftValidationResponse,
    QuestionGenerationSettings,
    QuestionGroupCreateRequest,
    QuestionGroupDifficultyBreakdown,
    QuestionGroupListResponse,
    QuestionGroupQuestionSummary,
    QuestionGroupRecord,
    QuestionGroupStatus,
    QuestionGroupUpdateRequest,
    QuestionListResponse,
    QuestionRecord,
    QuestionStatus,
    QuestionUpdateRequest,
    QuestionVisibility,
    ReferenceSolutionArtifact,
    SolutionValidationCaseResult,
    SolutionValidationReport,
    TestCase,
    ValidationStatus,
)

QuestionEnum = TypeVar("QuestionEnum", DifficultyLevel, QuestionStatus)

BULK_IMPORT_REQUIRED_HEADERS = {"title", "problem_statement", "difficulty"}
BULK_IMPORT_TEMPLATE_HEADERS = [
    "title",
    "problem_statement",
    "difficulty",
    "topics",
    "tags",
    "category",
    "constraints",
    "input_format",
    "input_explanation",
    "output_format",
    "output_explanation",
    "sample_test_cases",
    "hidden_test_cases",
    "reference_solution",
    "reference_language",
    "supported_languages",
    "answer_validation_mode",
    "output_checker",
    "output_checker_explanation",
    "execution_time_limit_seconds",
    "memory_limit_mb",
    "solution_approach",
    "time_complexity",
    "space_complexity",
    "status",
]


@dataclass(frozen=True)
class QuestionFilters:
    """Question list filters."""

    search: str | None = None
    difficulty: DifficultyLevel | None = None
    status: QuestionStatus | None = None
    tag: str | None = None
    sort_by: str | None = "date-desc"


@dataclass(frozen=True)
class QuestionGroupFilters:
    """Question group list filters."""

    search: str | None = None
    status: QuestionGroupStatus | None = None


class QuestionBankService:
    """Manage recruiter-owned coding questions."""

    def __init__(self, session: Session) -> None:
        self._repository = QuestionBankRepository(session)
        settings = get_settings()
        self._execution_adapter = build_execution_port(settings)
        self._question_generation_workflow = QuestionGenerationWorkflow(
            settings,
            AIGatewayService(settings, session),
            self._execution_adapter,
        )

    def list_questions(
        self,
        recruiter_uid: str,
        filters: QuestionFilters,
    ) -> QuestionListResponse:
        """Return recruiter questions with optional filters."""

        try:
            items = self._repository.list_questions(
                recruiter_uid=recruiter_uid,
                search=filters.search,
                difficulty=filters.difficulty,
                status=filters.status,
                tag=filters.tag,
                sort_by=filters.sort_by or "date-desc",
            )
        except SQLAlchemyError as exc:
            raise QuestionBankStoreUnavailableError(
                "Unable to read question bank",
            ) from exc

        records = [self._record_from_model(item) for item in items]
        return QuestionListResponse(items=records, total=len(records))

    def create_question(
        self,
        recruiter_uid: str,
        payload: QuestionCreateRequest,
    ) -> QuestionRecord:
        """Create a new recruiter question."""

        self._validate_question_payload(payload)
        supported_languages = self._normalize_languages(
            payload.supported_languages,
            payload.reference_language,
        )
        tags = normalize_question_tags([*payload.tags, *payload.topics], limit=6)
        answer_mode = AnswerValidationMode(
            normalize_answer_validation_mode(payload.answer_validation_mode),
        )
        checker_explanation = (
            payload.output_checker_explanation.strip()
            or default_checker_explanation(answer_mode)
        )
        model = QuestionBankQuestionModel(
            id=str(uuid4()),
            recruiter_uid=recruiter_uid,
            title=payload.title.strip(),
            problem_statement=payload.problem_statement.strip(),
            difficulty=payload.difficulty.value,
            topics=[],
            tags=tags,
            category=normalize_question_category(payload.category, tags),
            constraints=payload.constraints.strip(),
            input_format=payload.input_format.strip(),
            input_explanation=payload.input_explanation.strip(),
            output_format=payload.output_format.strip(),
            output_explanation=payload.output_explanation.strip(),
            sample_test_cases=self._dump_test_cases(
                payload.sample_test_cases,
                is_sample=True,
            ),
            hidden_test_cases=self._dump_test_cases(
                payload.hidden_test_cases,
                is_sample=False,
            ),
            reference_solution=payload.reference_solution.strip(),
            reference_language=payload.reference_language.strip() or "python",
            supported_languages=supported_languages,
            execution_time_limit_seconds=payload.execution_time_limit_seconds,
            memory_limit_mb=payload.memory_limit_mb,
            metadata_status=payload.metadata_status.value,
            difficulty_source=payload.difficulty_source.value,
            validation_report=(
                payload.validation_report.model_dump(mode="json")
                if payload.validation_report
                else None
            ),
            validation_status=payload.validation_status.value,
            validation_updated_at=payload.validation_updated_at,
            reference_solutions=self._dump_reference_solutions(
                payload.reference_solutions,
                payload.reference_language,
                payload.reference_solution,
            ),
            answer_validation_mode=answer_mode.value,
            output_checker=payload.output_checker.strip(),
            output_checker_explanation=checker_explanation,
            solution_approach=payload.solution_approach.strip(),
            time_complexity=payload.time_complexity.strip(),
            space_complexity=payload.space_complexity.strip(),
            status=payload.status.value,
            creation_mode=payload.creation_mode.value,
            visibility=payload.visibility.value,
        )

        try:
            self._repository.add(model)
            self._repository.commit()
            self._repository.refresh(model)
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise QuestionBankStoreUnavailableError(
                "Unable to create question",
            ) from exc

        return self._record_from_model(model)

    def bulk_import_questions(
        self,
        recruiter_uid: str,
        payload: QuestionBulkImportRequest,
    ) -> QuestionBulkImportResponse:
        """Create multiple recruiter questions from CSV text."""

        reader = csv.DictReader(StringIO(payload.csv_text.lstrip("\ufeff")))
        if not reader.fieldnames:
            raise QuestionBankValidationError("CSV file does not contain a header row.")

        header_map = {
            header.strip().lower(): header
            for header in reader.fieldnames
            if header and header.strip()
        }
        missing_headers = sorted(BULK_IMPORT_REQUIRED_HEADERS - set(header_map))
        if missing_headers:
            raise QuestionBankValidationError(
                "CSV is missing required column(s): " + ", ".join(missing_headers),
            )

        created: list[QuestionRecord] = []
        row_errors: list[QuestionBulkImportRowError] = []
        total_rows = 0

        for row_number, row in enumerate(reader, start=2):
            if self._csv_row_is_empty(row):
                continue
            total_rows += 1
            title = self._csv_value(row, header_map, "title")
            if row.get(None):
                row_errors.append(
                    QuestionBulkImportRowError(
                        row_number=row_number,
                        title=title,
                        errors=[
                            (
                                "Row has extra CSV values. Wrap fields containing "
                                "commas or newlines in quotes."
                            ),
                        ],
                    ),
                )
                continue
            try:
                question_payload = self._question_payload_from_csv_row(row, header_map)
                created.append(self.create_question(recruiter_uid, question_payload))
            except (QuestionBankValidationError, ValueError, ValidationError) as exc:
                row_errors.append(
                    QuestionBulkImportRowError(
                        row_number=row_number,
                        title=title,
                        errors=self._bulk_import_error_messages(exc),
                    ),
                )

        return QuestionBulkImportResponse(
            total_rows=total_rows,
            created_count=len(created),
            failed_count=len(row_errors),
            created=created,
            errors=row_errors,
        )

    def update_question(
        self,
        recruiter_uid: str,
        question_id: str,
        payload: QuestionUpdateRequest,
    ) -> QuestionRecord:
        """Update an existing recruiter question."""

        model = self._get_owned_question(recruiter_uid, question_id)
        if model is None:
            raise QuestionNotFoundError()

        self._validate_question_payload(payload)
        supported_languages = self._normalize_languages(
            payload.supported_languages,
            payload.reference_language,
        )
        tags = normalize_question_tags([*payload.tags, *payload.topics], limit=6)
        answer_mode = AnswerValidationMode(
            normalize_answer_validation_mode(payload.answer_validation_mode),
        )
        checker_explanation = (
            payload.output_checker_explanation.strip()
            or default_checker_explanation(answer_mode)
        )
        model.title = payload.title.strip()
        model.problem_statement = payload.problem_statement.strip()
        model.difficulty = payload.difficulty.value
        model.topics = []
        model.tags = tags
        model.category = normalize_question_category(payload.category, tags)
        model.constraints = payload.constraints.strip()
        model.input_format = payload.input_format.strip()
        model.input_explanation = payload.input_explanation.strip()
        model.output_format = payload.output_format.strip()
        model.output_explanation = payload.output_explanation.strip()
        model.sample_test_cases = self._dump_test_cases(
            payload.sample_test_cases,
            is_sample=True,
        )
        model.hidden_test_cases = self._dump_test_cases(
            payload.hidden_test_cases,
            is_sample=False,
        )
        model.reference_solution = payload.reference_solution.strip()
        model.reference_language = payload.reference_language.strip() or "python"
        model.supported_languages = supported_languages
        model.execution_time_limit_seconds = payload.execution_time_limit_seconds
        model.memory_limit_mb = payload.memory_limit_mb
        model.metadata_status = payload.metadata_status.value
        model.difficulty_source = payload.difficulty_source.value
        model.validation_report = (
            payload.validation_report.model_dump(mode="json")
            if payload.validation_report
            else None
        )
        model.validation_status = payload.validation_status.value
        model.validation_updated_at = payload.validation_updated_at
        model.reference_solutions = self._dump_reference_solutions(
            payload.reference_solutions,
            payload.reference_language,
            payload.reference_solution,
        )
        model.answer_validation_mode = answer_mode.value
        model.output_checker = payload.output_checker.strip()
        model.output_checker_explanation = checker_explanation
        model.solution_approach = payload.solution_approach.strip()
        model.time_complexity = payload.time_complexity.strip()
        model.space_complexity = payload.space_complexity.strip()
        model.status = payload.status.value
        model.visibility = payload.visibility.value

        try:
            self._repository.commit()
            self._repository.refresh(model)
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise QuestionBankStoreUnavailableError(
                "Unable to update question",
            ) from exc

        return self._record_from_model(model)

    def delete_question(self, recruiter_uid: str, question_id: str) -> None:
        """Delete a recruiter question."""

        model = self._get_owned_question(recruiter_uid, question_id)
        if model is None:
            raise QuestionNotFoundError()

        try:
            self._repository.delete(model)
            self._repository.commit()
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise QuestionBankStoreUnavailableError(
                "Unable to delete question",
            ) from exc

    def list_groups(
        self,
        recruiter_uid: str,
        filters: QuestionGroupFilters,
    ) -> QuestionGroupListResponse:
        """Return recruiter question groups with live question details."""

        try:
            items = self._repository.list_groups(
                recruiter_uid=recruiter_uid,
                search=filters.search,
                status=filters.status,
            )
        except SQLAlchemyError as exc:
            raise QuestionBankStoreUnavailableError(
                "Unable to read question groups",
            ) from exc

        records = [self._group_record_from_model(item, recruiter_uid) for item in items]
        return QuestionGroupListResponse(items=records, total=len(records))

    def create_group(
        self,
        recruiter_uid: str,
        payload: QuestionGroupCreateRequest,
    ) -> QuestionGroupRecord:
        """Create a reusable question group."""

        question_ids = self._validate_question_ids(recruiter_uid, payload.question_ids)
        model = QuestionGroupModel(
            id=str(uuid4()),
            recruiter_uid=recruiter_uid,
            name=payload.name.strip(),
            description=payload.description.strip(),
            question_ids=question_ids,
            status=payload.status.value,
        )

        try:
            self._repository.add(model)
            self._repository.commit()
            self._repository.refresh(model)
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise QuestionBankStoreUnavailableError(
                "Unable to create question group",
            ) from exc

        return self._group_record_from_model(model, recruiter_uid)

    def update_group(
        self,
        recruiter_uid: str,
        group_id: str,
        payload: QuestionGroupUpdateRequest,
    ) -> QuestionGroupRecord:
        """Update an existing question group."""

        model = self._get_owned_group(recruiter_uid, group_id)
        if model is None:
            raise QuestionNotFoundError("Question group not found")

        question_ids = self._validate_question_ids(recruiter_uid, payload.question_ids)
        model.name = payload.name.strip()
        model.description = payload.description.strip()
        model.question_ids = question_ids
        model.status = payload.status.value

        try:
            self._repository.commit()
            self._repository.refresh(model)
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise QuestionBankStoreUnavailableError(
                "Unable to update question group",
            ) from exc

        return self._group_record_from_model(model, recruiter_uid)

    def delete_group(self, recruiter_uid: str, group_id: str) -> None:
        """Delete a question group."""

        model = self._get_owned_group(recruiter_uid, group_id)
        if model is None:
            raise QuestionNotFoundError("Question group not found")

        try:
            self._repository.delete(model)
            self._repository.commit()
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise QuestionBankStoreUnavailableError(
                "Unable to delete question group",
            ) from exc

    def generate_ai_draft(
        self,
        recruiter_uid: str,
        request: QuestionAIDraftRequest,
    ) -> QuestionAIDraftResponse:
        """Generate a recruiter-ready draft using the LangGraph workflow."""

        self._assert_ai_draft_input_guardrails(request)

        existing_questions = self.list_questions(
            recruiter_uid,
            QuestionFilters(),
        ).items
        response = self._question_generation_workflow.generate(
            recruiter_uid=recruiter_uid,
            request=request,
            existing_questions=existing_questions,
        )

        # 2. Post-model output solutions SAST check
        if response.draft:
            self._assert_output_checker_guardrails(response.draft.output_checker)
            primary_sast_error = check_code_sast(
                response.draft.reference_solution,
                response.draft.reference_language,
            )
            if primary_sast_error:
                raise QuestionGuardrailError(primary_sast_error)
            for lang_sol in (response.draft.reference_solutions or {}).values():
                secondary_sast_error = check_code_sast(
                    lang_sol.source_code,
                    lang_sol.language,
                )
                if secondary_sast_error:
                    raise QuestionGuardrailError(secondary_sast_error)

        return response

    def stream_ai_draft_events(
        self,
        recruiter_uid: str,
        request: QuestionAIDraftRequest,
    ) -> Iterator[dict[str, object]]:
        """Stream question generation graph progress events."""

        self._assert_ai_draft_input_guardrails(request)

        existing_questions = self.list_questions(
            recruiter_uid,
            QuestionFilters(),
        ).items
        for event in self._question_generation_workflow.generate_events(
            recruiter_uid=recruiter_uid,
            request=request,
            existing_questions=existing_questions,
        ):
            # 2. Post-model output solutions SAST check on completion event
            if event.get("type") == "complete" and "response" in event:
                draft_dict = event["response"].get("draft")
                if draft_dict:
                    primary_sol = draft_dict.get("reference_solution")
                    ref_lang = draft_dict.get("reference_language")
                    self._assert_output_checker_guardrails(
                        str(draft_dict.get("output_checker") or ""),
                    )
                    primary_sast_error = check_code_sast(primary_sol, ref_lang)
                    if primary_sast_error:
                        raise QuestionGuardrailError(primary_sast_error)
                    ref_sols = draft_dict.get("reference_solutions") or {}
                    for lang_sol in ref_sols.values():
                        secondary_sast_error = check_code_sast(
                            lang_sol.get("source_code"), lang_sol.get("language")
                        )
                        if secondary_sast_error:
                            raise QuestionGuardrailError(secondary_sast_error)

            provider, model = self._question_generation_workflow.current_ai_target
            yield {
                **event,
                "ai_provider": provider,
                "ai_model": model,
            }

    def validate_draft(
        self,
        request: QuestionDraftValidationRequest,
    ) -> QuestionDraftValidationResponse:
        """Run an unsaved draft through the execution engine."""

        self._assert_output_checker_guardrails(request.draft.output_checker)
        report = self._validate_reference_solution(
            request.draft.reference_solution,
            request.draft.reference_language,
            request.draft.sample_test_cases,
            request.draft.hidden_test_cases,
            request.draft.execution_time_limit_seconds,
            request.draft.memory_limit_mb,
            request.draft.answer_validation_mode,
            request.draft.output_checker,
            request.draft.output_checker_explanation,
        )
        return QuestionDraftValidationResponse(validation_report=report)

    def refine_draft_test_cases(
        self,
        recruiter_uid: str,
        request: QuestionDraftRefinementRequest,
    ) -> QuestionDraftRefinementResponse:
        """Repair existing testcase outputs using execution and semantic review."""

        self._assert_refinement_input_guardrails(request)
        return self._question_generation_workflow.refine_test_cases(
            recruiter_uid,
            request.draft,
            request.generation_settings,
        )

    def refine_draft_solution(
        self,
        recruiter_uid: str,
        request: QuestionDraftRefinementRequest,
    ) -> QuestionDraftRefinementResponse:
        """Repair existing source using the problem contract and failure evidence."""

        self._assert_refinement_input_guardrails(request)
        return self._question_generation_workflow.refine_solution(
            recruiter_uid,
            request.draft,
            request.generation_settings,
        )

    def _assert_ai_draft_input_guardrails(
        self,
        request: QuestionAIDraftRequest,
    ) -> None:
        """Reject unsafe user-controlled context before calling the question agent."""

        for label, value in self._ai_draft_guardrail_inputs(request):
            input_error = check_input_guardrails(value)
            if input_error:
                raise QuestionGuardrailError(f"{label}: {input_error}")
        if request.current_draft is not None:
            self._assert_output_checker_guardrails(request.current_draft.output_checker)

    def _assert_refinement_input_guardrails(
        self,
        request: QuestionDraftRefinementRequest,
    ) -> None:
        """Reject unsafe refinement context before repair agents see it."""

        for label, value in self._draft_context_guardrail_inputs(request.draft):
            input_error = check_input_guardrails(value)
            if input_error:
                raise QuestionGuardrailError(f"{label}: {input_error}")
        self._assert_output_checker_guardrails(request.draft.output_checker)
        if request.generation_settings is not None:
            for label, value in self._settings_guardrail_inputs(
                request.generation_settings,
            ):
                input_error = check_input_guardrails(value)
                if input_error:
                    raise QuestionGuardrailError(f"{label}: {input_error}")

    @staticmethod
    def _assert_output_checker_guardrails(source: str) -> None:
        checker_source = source.strip()
        if not checker_source:
            return
        checker_sast_error = check_code_sast(checker_source, "python")
        if checker_sast_error:
            raise QuestionGuardrailError(f"Output checker: {checker_sast_error}")
        checker_error = validate_output_checker_source(checker_source)
        if checker_error:
            raise QuestionGuardrailError(checker_error)

    def _ai_draft_guardrail_inputs(
        self,
        request: QuestionAIDraftRequest,
    ) -> Iterator[tuple[str, str]]:
        yield "AI prompt", request.prompt
        if request.title_hint:
            yield "Title hint", request.title_hint
        if request.target_language:
            yield "Target language", request.target_language
        for index, tag in enumerate(request.focus_tags, start=1):
            yield f"Focus tag {index}", tag
        yield from self._settings_guardrail_inputs(request.generation_settings)
        if request.current_draft is not None:
            yield from self._draft_context_guardrail_inputs(request.current_draft)

    @staticmethod
    def _settings_guardrail_inputs(
        settings: QuestionGenerationSettings,
    ) -> Iterator[tuple[str, str]]:
        for index, topic in enumerate(settings.topics, start=1):
            yield f"Generation topic {index}", topic
        for index, language in enumerate(settings.supported_languages, start=1):
            yield f"Supported language {index}", language
        yield "Interview style", settings.interview_style
        yield "Company style", settings.company_style

    @staticmethod
    def _draft_context_guardrail_inputs(
        draft: QuestionAIDraftContext,
    ) -> Iterator[tuple[str, str]]:
        text_fields = {
            "Draft title": draft.title,
            "Draft problem statement": draft.problem_statement,
            "Draft category": draft.category,
            "Draft constraints": draft.constraints,
            "Draft input format": draft.input_format,
            "Draft input explanation": draft.input_explanation,
            "Draft output format": draft.output_format,
            "Draft output explanation": draft.output_explanation,
            "Draft output checker explanation": draft.output_checker_explanation,
            "Draft reference solution": draft.reference_solution,
            "Draft solution approach": draft.solution_approach,
            "Draft time complexity": draft.time_complexity,
            "Draft space complexity": draft.space_complexity,
        }
        yield from text_fields.items()
        for index, topic in enumerate(draft.topics, start=1):
            yield f"Draft topic {index}", topic
        for index, tag in enumerate(draft.tags, start=1):
            yield f"Draft tag {index}", tag
        for index, test_case in enumerate(draft.sample_test_cases, start=1):
            yield f"Sample testcase {index} explanation", test_case.explanation
        for index, test_case in enumerate(draft.hidden_test_cases, start=1):
            yield f"Hidden testcase {index} explanation", test_case.explanation
        for language, artifact in draft.reference_solutions.items():
            label = language or artifact.language
            yield f"{label} reference solution", artifact.source_code
            for index, note in enumerate(artifact.notes, start=1):
                yield f"{label} reference solution note {index}", note

    def _question_payload_from_csv_row(
        self,
        row: dict[str, str | None],
        header_map: dict[str, str],
    ) -> QuestionCreateRequest:
        """Convert one CSV row into the normal create-question payload."""

        difficulty = self._parse_enum_value(
            self._csv_value(row, header_map, "difficulty"),
            DifficultyLevel,
            "difficulty",
        )
        status_text = (
            self._csv_value(row, header_map, "status") or QuestionStatus.DRAFT.value
        )
        status = self._parse_enum_value(status_text, QuestionStatus, "status")
        reference_language = (
            self._csv_value(row, header_map, "reference_language") or "python"
        ).lower()

        return QuestionCreateRequest(
            title=self._csv_value(row, header_map, "title"),
            problem_statement=self._csv_value(row, header_map, "problem_statement"),
            difficulty=difficulty,
            topics=self._split_import_tokens(
                self._csv_value(row, header_map, "topics"),
            ),
            tags=self._split_import_tokens(self._csv_value(row, header_map, "tags")),
            category=self._csv_value(row, header_map, "category"),
            constraints=self._csv_value(row, header_map, "constraints"),
            input_format=self._csv_value(row, header_map, "input_format"),
            input_explanation=self._csv_value(row, header_map, "input_explanation"),
            output_format=self._csv_value(row, header_map, "output_format"),
            output_explanation=self._csv_value(row, header_map, "output_explanation"),
            sample_test_cases=self._parse_import_test_cases(
                self._csv_value(row, header_map, "sample_test_cases"),
                "sample_test_cases",
            ),
            hidden_test_cases=self._parse_import_test_cases(
                self._csv_value(row, header_map, "hidden_test_cases"),
                "hidden_test_cases",
            ),
            reference_solution=self._csv_value(row, header_map, "reference_solution"),
            reference_language=reference_language,
            supported_languages=self._split_import_tokens(
                self._csv_value(row, header_map, "supported_languages"),
            )
            or [reference_language],
            answer_validation_mode=AnswerValidationMode(
                normalize_answer_validation_mode(
                    self._csv_value(row, header_map, "answer_validation_mode")
                    or AnswerValidationMode.EXACT.value,
                ),
            ),
            output_checker=self._csv_value(row, header_map, "output_checker"),
            output_checker_explanation=self._csv_value(
                row,
                header_map,
                "output_checker_explanation",
            ),
            execution_time_limit_seconds=self._parse_optional_int(
                self._csv_value(row, header_map, "execution_time_limit_seconds"),
                2,
            ),
            memory_limit_mb=self._parse_optional_int(
                self._csv_value(row, header_map, "memory_limit_mb"),
                256,
            ),
            metadata_status=MetadataStatus.CLASSIFIED,
            difficulty_source=DifficultySource.LEGACY,
            solution_approach=self._csv_value(row, header_map, "solution_approach"),
            time_complexity=self._csv_value(row, header_map, "time_complexity"),
            space_complexity=self._csv_value(row, header_map, "space_complexity"),
            status=status,
            creation_mode=QuestionCreationMode.MANUAL,
        )

    @staticmethod
    def _csv_value(
        row: dict[str, str | None],
        header_map: dict[str, str],
        key: str,
    ) -> str:
        header = header_map.get(key)
        if not header:
            return ""
        value = row.get(header)
        return value.strip() if value else ""

    @staticmethod
    def _csv_row_is_empty(row: dict[str, str | None]) -> bool:
        return not any(value and value.strip() for key, value in row.items() if key)

    @staticmethod
    def _split_import_tokens(value: str) -> list[str]:
        return [
            token.strip().lower()
            for token in value.replace(";", ",").split(",")
            if token.strip()
        ]

    @staticmethod
    def _parse_optional_int(value: str, default: int) -> int:
        if not value.strip():
            return default
        return int(value.strip())

    @staticmethod
    def _parse_enum_value(
        value: str,
        enum_type: type[QuestionEnum],
        label: str,
    ) -> QuestionEnum:
        normalized = value.strip().lower()
        try:
            return enum_type(normalized)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in enum_type)
            raise ValueError(f"{label} must be one of: {allowed}.") from exc

    @classmethod
    def _parse_import_test_cases(cls, value: str, label: str) -> list[TestCase]:
        if not value.strip():
            return []

        try:
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                raise ValueError(f"{label} must be a JSON array.")
            return [TestCase.model_validate(item) for item in parsed]
        except json.JSONDecodeError:
            return cls._parse_compact_test_cases(value, label)

    @staticmethod
    def _parse_compact_test_cases(value: str, label: str) -> list[TestCase]:
        cases: list[TestCase] = []
        for raw_case in value.split("||"):
            candidate = raw_case.strip()
            if not candidate:
                continue
            if "=>" not in candidate:
                raise ValueError(
                    f"{label} must be JSON or compact input=>expected pairs.",
                )
            test_input, expected_output = candidate.split("=>", 1)
            cases.append(
                TestCase(
                    input=test_input.strip().replace("\\n", "\n"),
                    expected_output=expected_output.strip().replace("\\n", "\n"),
                ),
            )
        return cases

    @staticmethod
    def _bulk_import_error_messages(
        error: QuestionBankValidationError | ValueError | ValidationError,
    ) -> list[str]:
        if isinstance(error, ValidationError):
            messages: list[str] = []
            for item in error.errors():
                location = ".".join(str(part) for part in item.get("loc", ()))
                message = str(item.get("msg", "Invalid value."))
                messages.append(f"{location}: {message}" if location else message)
            return messages or ["Invalid row."]
        message = getattr(error, "message", str(error))
        return [message]

    def _get_owned_question(
        self,
        recruiter_uid: str,
        question_id: str,
    ) -> QuestionBankQuestionModel | None:
        """Return one question owned by the recruiter."""

        try:
            return self._repository.get_owned_question(
                recruiter_uid=recruiter_uid,
                question_id=question_id,
            )
        except SQLAlchemyError as exc:
            raise QuestionBankStoreUnavailableError(
                "Unable to read question",
            ) from exc

    def _get_owned_group(
        self,
        recruiter_uid: str,
        group_id: str,
    ) -> QuestionGroupModel | None:
        """Return one group owned by the recruiter."""

        try:
            return self._repository.get_owned_group(
                recruiter_uid=recruiter_uid,
                group_id=group_id,
            )
        except SQLAlchemyError as exc:
            raise QuestionBankStoreUnavailableError(
                "Unable to read question group",
            ) from exc

    def _validate_question_ids(
        self,
        recruiter_uid: str,
        question_ids: list[str],
    ) -> list[str]:
        """Ensure selected question ids exist and belong to the recruiter."""

        normalized = self._normalize_question_ids(question_ids)
        if not normalized:
            raise QuestionBankValidationError(
                "A group must contain at least one existing question",
            )

        try:
            existing_ids = self._repository.existing_question_ids(
                recruiter_uid=recruiter_uid,
                question_ids=normalized,
            )
        except SQLAlchemyError as exc:
            raise QuestionBankStoreUnavailableError(
                "Unable to validate group questions",
            ) from exc

        missing_ids = [
            question_id for question_id in normalized if question_id not in existing_ids
        ]
        if missing_ids:
            raise QuestionBankValidationError(
                "One or more selected questions do not exist in the question bank",
            )

        return normalized

    @staticmethod
    def _dump_test_cases(
        test_cases: list[TestCase],
        *,
        is_sample: bool,
    ) -> list[dict[str, object]]:
        """Persist test cases with the correct sample/hidden bucket marker."""

        return [
            case.model_copy(update={"is_sample": is_sample}).model_dump(mode="json")
            for case in test_cases
        ]

    @staticmethod
    def _dump_reference_solutions(
        artifacts: dict[str, ReferenceSolutionArtifact],
        reference_language: str,
        reference_solution: str,
    ) -> dict[str, object]:
        """Persist multi-language solutions, mirroring the legacy primary solution."""

        normalized: dict[str, object] = {
            QuestionBankService._normalize_solution_language(
                language,
            ): artifact.model_dump(mode="json")
            for language, artifact in artifacts.items()
            if language.strip()
        }
        primary_language = QuestionBankService._normalize_solution_language(
            reference_language,
        )
        if reference_solution.strip() and primary_language not in normalized:
            normalized[primary_language] = ReferenceSolutionArtifact(
                language=primary_language,
                source_code=reference_solution.strip(),
            ).model_dump(mode="json")
        return normalized

    @staticmethod
    def _validate_question_payload(
        payload: QuestionCreateRequest | QuestionUpdateRequest,
    ) -> None:
        """Enforce lifecycle-specific question requirements."""

        answer_mode = AnswerValidationMode(
            normalize_answer_validation_mode(payload.answer_validation_mode),
        )
        checker_source = payload.output_checker.strip()
        if checker_source:
            checker_sast_error = check_code_sast(checker_source, "python")
            if checker_sast_error:
                raise QuestionGuardrailError(
                    f"Output checker: {checker_sast_error}",
                )
            checker_error = validate_output_checker_source(checker_source)
            if checker_error:
                raise QuestionBankValidationError(checker_error)

        if payload.status != QuestionStatus.VALIDATED:
            return

        missing: list[str] = []
        if len(payload.problem_statement.strip()) < 20:
            missing.append("a problem statement with at least 20 characters")
        if not payload.constraints.strip():
            missing.append("constraints")
        if not payload.reference_solution.strip():
            missing.append("reference solution")
        if not QuestionBankService._has_complete_test_case(payload.sample_test_cases):
            missing.append("at least one complete sample test case")
        if not QuestionBankService._has_complete_test_case(payload.hidden_test_cases):
            missing.append("at least one complete hidden test case")
        if not payload.supported_languages:
            missing.append("at least one supported language")
        if payload.validation_status != ValidationStatus.PASSED:
            missing.append("a passing execution validation")
        if payload.metadata_status != MetadataStatus.CLASSIFIED:
            missing.append("AI metadata classification")
        if (
            answer_mode
            in {
                AnswerValidationMode.MULTIPLE_VALID,
                AnswerValidationMode.CONSTRUCTIVE,
            }
            and not checker_source
        ):
            missing.append("a safe custom output checker")

        if missing:
            raise QuestionBankValidationError(
                "Validated questions require "
                + ", ".join(missing)
                + ". Save as draft until these sections are ready.",
            )

    def _validate_reference_solution(
        self,
        source_code: str,
        language: str,
        sample_test_cases: list[TestCase],
        hidden_test_cases: list[TestCase],
        execution_time_limit_seconds: int,
        memory_limit_mb: int,
        answer_validation_mode: str | AnswerValidationMode = AnswerValidationMode.EXACT,
        output_checker: str = "",
        output_checker_explanation: str = "",
    ) -> SolutionValidationReport:
        """Execute a draft reference solution against sample and hidden tests."""

        source = source_code.strip()
        answer_mode = AnswerValidationMode(
            normalize_answer_validation_mode(answer_validation_mode),
        )
        checker_source = output_checker.strip()
        checker_explanation = (
            output_checker_explanation.strip()
            or default_checker_explanation(answer_mode)
        )
        sample_tests = [
            case.model_copy(update={"is_sample": True})
            for case in sample_test_cases
            if case.expected_output.strip()
        ]
        hidden_tests = [
            case.model_copy(update={"is_sample": False})
            for case in hidden_test_cases
            if case.expected_output.strip()
        ]
        if not source:
            return SolutionValidationReport(
                status=ValidationStatus.SKIPPED.value,
                summary=(
                    "Execution validation skipped because the reference solution "
                    "is empty."
                ),
                runner_notes=["Add a complete STDIN/STDOUT reference program first."],
            )
        if not sample_tests and not hidden_tests:
            return SolutionValidationReport(
                status=ValidationStatus.SKIPPED.value,
                summary=(
                    "Execution validation skipped because no complete test cases exist."
                ),
                runner_notes=["Add at least one sample or hidden testcase first."],
            )

        contract_error = self._reference_solution_contract_error(source, language)
        if contract_error:
            return SolutionValidationReport(
                status=ValidationStatus.FAILED.value,
                summary=(
                    "Reference solution is not complete runnable "
                    f"{self._normalize_solution_language(language)} source code."
                ),
                passed_count=0,
                failed_count=len(sample_tests) + len(hidden_tests),
                sample_count=len(sample_tests),
                hidden_count=len(hidden_tests),
                runner_notes=[
                    contract_error,
                    (
                        "Expected complete CodeChef-style source code with a solve "
                        "helper and stdin/stdout runner, not an algorithm name or "
                        "written explanation."
                    ),
                ],
            )

        results: list[SolutionValidationCaseResult] = []
        memory_limit_kb = memory_limit_mb * 1024 if memory_limit_mb else None
        try:
            if sample_tests:
                sample_results, _, _ = self._execution_adapter.execute_batch(
                    source_code=source,
                    language=language.strip().lower() or "python",
                    test_cases=sample_tests,
                    run_type="question_bank_sample_validation",
                    time_limit_seconds=execution_time_limit_seconds,
                    memory_limit_kb=memory_limit_kb,
                )
                for index, result in enumerate(sample_results, start=1):
                    scored_result = apply_answer_validation(
                        result,
                        mode=answer_mode,
                        checker_source=checker_source,
                    )
                    results.append(
                        SolutionValidationCaseResult(
                            bucket="sample",
                            index=index,
                            passed=scored_result.passed,
                            status=scored_result.status,
                            stdin=scored_result.input,
                            expected_output=scored_result.expected_output,
                            actual_output=scored_result.actual_output,
                            stderr=scored_result.stderr,
                            compile_output=scored_result.compile_output,
                            message=scored_result.message,
                            checker_message=scored_result.checker_message,
                            token=scored_result.token,
                            execution_time=scored_result.execution_time,
                            memory_kb=scored_result.memory_kb,
                        )
                    )
            if hidden_tests:
                hidden_results, _, _ = self._execution_adapter.execute_batch(
                    source_code=source,
                    language=language.strip().lower() or "python",
                    test_cases=hidden_tests,
                    run_type="question_bank_hidden_validation",
                    time_limit_seconds=execution_time_limit_seconds,
                    memory_limit_kb=memory_limit_kb,
                )
                for index, result in enumerate(hidden_results, start=1):
                    scored_result = apply_answer_validation(
                        result,
                        mode=answer_mode,
                        checker_source=checker_source,
                    )
                    results.append(
                        SolutionValidationCaseResult(
                            bucket="hidden",
                            index=index,
                            passed=scored_result.passed,
                            status=scored_result.status,
                            stdin=scored_result.input,
                            expected_output=scored_result.expected_output,
                            actual_output=scored_result.actual_output,
                            stderr=scored_result.stderr,
                            compile_output=scored_result.compile_output,
                            message=scored_result.message,
                            checker_message=scored_result.checker_message,
                            token=scored_result.token,
                            execution_time=scored_result.execution_time,
                            memory_kb=scored_result.memory_kb,
                        )
                    )
        except ExecutionAdapterError as exc:
            return SolutionValidationReport(
                status=ValidationStatus.FAILED.value,
                summary=f"Execution validation failed: {str(exc)}",
                passed_count=0,
                failed_count=len(sample_tests) + len(hidden_tests),
                sample_count=len(sample_tests),
                hidden_count=len(hidden_tests),
                runner_notes=[
                    str(exc),
                    "Ensure the code-execution-service is running and healthy.",
                ],
                results=[],
            )

        passed_count = sum(1 for item in results if item.passed)
        failed_count = len(results) - passed_count
        status = (
            ValidationStatus.PASSED if failed_count == 0 else ValidationStatus.FAILED
        )
        summary = (
            f"Reference solution passed {passed_count}/{len(results)} execution checks."
            if status == ValidationStatus.PASSED
            else (
                f"Reference solution failed {failed_count} of {len(results)} "
                "execution checks."
            )
        )
        return SolutionValidationReport(
            status=status.value,
            summary=summary,
            passed_count=passed_count,
            failed_count=failed_count,
            sample_count=len(sample_tests),
            hidden_count=len(hidden_tests),
            runner_notes=[
                "Validated as a complete CodeChef-style STDIN/STDOUT program.",
                f"Answer validation mode: {answer_mode.value}.",
                checker_explanation,
            ],
            results=results,
        )

    @staticmethod
    def _has_complete_test_case(test_cases: list[TestCase]) -> bool:
        """Return true when at least one test has an expected output."""

        return any(test_case.expected_output.strip() for test_case in test_cases)

    @staticmethod
    def _normalize_solution_language(language: str) -> str:
        normalized = language.strip().lower()
        if normalized in {"py", "python3"}:
            return "python"
        if normalized in {"c++", "cplusplus"}:
            return "cpp"
        return normalized or "python"

    @classmethod
    def _reference_solution_contract_error(cls, source_code: str, language: str) -> str:
        """Return an error when the reference solution is prose, not source code."""

        stripped = source_code.strip()
        if not stripped:
            return "The reference_solution field is empty."

        normalized_language = cls._normalize_solution_language(language)
        lower_source = stripped.lower()
        forbidden_markers = [
            "todo",
            "pseudocode",
            "algorithm:",
            "approach:",
            "complexity:",
            "not implemented",
        ]
        if any(marker in lower_source for marker in forbidden_markers):
            return (
                "The reference_solution contains explanation/TODO text instead "
                "of final runnable source code."
            )

        required_markers = {
            "python": ["def solve", "__main__"],
            "java": ["class main", "public static void main", "solve("],
            "cpp": ["#include", "int main", "solve("],
            "c": ["#include", "int main", "solve("],
            "javascript": ["function solve", "process.stdin"],
            "js": ["function solve", "process.stdin"],
        }
        markers = required_markers.get(normalized_language, ["solve", "main"])
        if all(marker in lower_source for marker in markers):
            return ""

        plain_text_indicators = [
            "algorithm",
            "use ",
            "using ",
            "sort the",
            "dynamic programming",
            "kadane",
            "two pointer",
            "binary search",
        ]
        if len(stripped.splitlines()) <= 2 or any(
            indicator in lower_source for indicator in plain_text_indicators
        ):
            return (
                "The reference_solution appears to be an algorithm name or "
                "plain-English approach, not source code."
            )

        return (
            "The reference_solution is missing the required solve helper and "
            "stdin/stdout runner markers for the selected language."
        )

    @staticmethod
    def _normalize_languages(
        values: list[str],
        reference_language: str,
    ) -> list[str]:
        """Return normalized supported languages including the reference language."""

        languages: list[str] = []
        for value in values:
            normalized = QuestionBankService._normalize_solution_language(value)
            if normalized and normalized not in languages:
                languages.append(normalized)
        reference = QuestionBankService._normalize_solution_language(
            reference_language,
        )
        if reference not in languages:
            languages.insert(0, reference)
        return languages

    @staticmethod
    def _record_from_model(
        model: QuestionBankQuestionModel,
    ) -> QuestionRecord:
        """Map the ORM model to an API record."""

        tags = normalize_question_tags(
            [
                *list(model.tags or []),
                *list(getattr(model, "topics", []) or []),
            ],
            limit=6,
        )
        answer_mode = AnswerValidationMode(
            normalize_answer_validation_mode(
                getattr(
                    model,
                    "answer_validation_mode",
                    AnswerValidationMode.EXACT.value,
                ),
            ),
        )
        checker_explanation = (
            getattr(model, "output_checker_explanation", "") or ""
        ).strip() or default_checker_explanation(answer_mode)
        return QuestionRecord(
            id=model.id,
            recruiter_uid=model.recruiter_uid,
            title=model.title,
            problem_statement=model.problem_statement,
            difficulty=DifficultyLevel(model.difficulty),
            topics=[],
            tags=tags,
            category=normalize_question_category(
                getattr(model, "category", "") or "",
                tags,
            ),
            constraints=model.constraints,
            input_format=model.input_format,
            input_explanation=getattr(model, "input_explanation", "") or "",
            output_format=model.output_format,
            output_explanation=getattr(model, "output_explanation", "") or "",
            sample_test_cases=[
                TestCase.model_validate({**case, "is_sample": True})
                for case in model.sample_test_cases
            ],
            hidden_test_cases=[
                TestCase.model_validate({**case, "is_sample": False})
                for case in model.hidden_test_cases
            ],
            reference_solution=model.reference_solution,
            reference_language=model.reference_language,
            supported_languages=list(model.supported_languages or []),
            execution_time_limit_seconds=getattr(
                model,
                "execution_time_limit_seconds",
                2,
            )
            or 2,
            memory_limit_mb=getattr(model, "memory_limit_mb", 256) or 256,
            metadata_status=MetadataStatus(
                getattr(model, "metadata_status", MetadataStatus.PENDING.value)
                or MetadataStatus.PENDING.value,
            ),
            difficulty_source=DifficultySource(
                getattr(model, "difficulty_source", DifficultySource.LEGACY.value)
                or DifficultySource.LEGACY.value,
            ),
            validation_report=(
                SolutionValidationReport.model_validate(model.validation_report)
                if getattr(model, "validation_report", None)
                else None
            ),
            validation_status=ValidationStatus(
                getattr(model, "validation_status", ValidationStatus.NOT_RUN.value)
                or ValidationStatus.NOT_RUN.value,
            ),
            validation_updated_at=getattr(model, "validation_updated_at", None),
            reference_solutions={
                language: ReferenceSolutionArtifact.model_validate(artifact)
                for language, artifact in (
                    getattr(model, "reference_solutions", {}) or {}
                ).items()
            },
            answer_validation_mode=answer_mode,
            output_checker=getattr(model, "output_checker", "") or "",
            output_checker_explanation=checker_explanation,
            solution_approach=getattr(model, "solution_approach", "") or "",
            time_complexity=getattr(model, "time_complexity", "") or "",
            space_complexity=getattr(model, "space_complexity", "") or "",
            status=QuestionStatus(model.status),
            creation_mode=QuestionCreationMode(model.creation_mode),
            visibility=QuestionVisibility(
                getattr(model, "visibility", QuestionVisibility.PRIVATE.value)
                or QuestionVisibility.PRIVATE.value,
            ),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _group_record_from_model(
        self,
        model: QuestionGroupModel,
        recruiter_uid: str,
    ) -> QuestionGroupRecord:
        """Map a group ORM model to an API record."""

        questions = self._load_questions_for_ids(
            recruiter_uid, list(model.question_ids or [])
        )
        difficulty_breakdown = QuestionGroupDifficultyBreakdown(
            easy=sum(
                1 for item in questions if item.difficulty == DifficultyLevel.EASY
            ),
            medium=sum(
                1 for item in questions if item.difficulty == DifficultyLevel.MEDIUM
            ),
            hard=sum(
                1 for item in questions if item.difficulty == DifficultyLevel.HARD
            ),
        )
        topics = self._merge_tokens(
            *(item.topics or item.tags for item in questions),
        )
        languages = self._merge_tokens(
            *(item.supported_languages for item in questions)
        )
        total_marks = sum(
            self._marks_for_question(item.difficulty) for item in questions
        )

        return QuestionGroupRecord(
            id=model.id,
            recruiter_uid=model.recruiter_uid,
            name=model.name,
            description=model.description,
            question_ids=list(model.question_ids or []),
            status=QuestionGroupStatus(model.status),
            questions=[
                QuestionGroupQuestionSummary(
                    id=item.id,
                    title=item.title,
                    difficulty=item.difficulty,
                    status=item.status,
                )
                for item in questions
            ],
            question_count=len(questions),
            difficulty_breakdown=difficulty_breakdown,
            topics=topics,
            languages=languages,
            total_marks=total_marks,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _load_questions_for_ids(
        self,
        recruiter_uid: str,
        question_ids: list[str],
    ) -> list[QuestionRecord]:
        """Load a list of recruiter-owned questions by id."""

        if not question_ids:
            return []

        try:
            models = self._repository.load_questions_by_ids(
                recruiter_uid=recruiter_uid,
                question_ids=question_ids,
            )
        except SQLAlchemyError as exc:
            raise QuestionBankStoreUnavailableError(
                "Unable to load group questions",
            ) from exc

        record_by_id = {item.id: self._record_from_model(item) for item in models}
        return [
            record_by_id[question_id]
            for question_id in question_ids
            if question_id in record_by_id
        ]

    @staticmethod
    def _normalize_question_ids(values: list[str]) -> list[str]:
        """Return de-duplicated question ids without changing their value."""

        seen: set[str] = set()
        ids: list[str] = []
        for value in values:
            question_id = value.strip()
            if question_id and question_id not in seen:
                ids.append(question_id)
                seen.add(question_id)
        return ids

    @staticmethod
    def _normalize_tokens(values: list[str]) -> list[str]:
        """Return de-duplicated, normalized tokens."""

        seen: set[str] = set()
        tokens: list[str] = []
        for value in values:
            token = value.strip().lower()
            if token and token not in seen:
                tokens.append(token)
                seen.add(token)
        return tokens

    @staticmethod
    def _merge_tokens(*groups: list[str]) -> list[str]:
        """Merge multiple token groups into one normalized list."""

        merged: list[str] = []
        for group in groups:
            merged.extend(group)
        return QuestionBankService._normalize_tokens(merged)

    @staticmethod
    def _marks_for_question(difficulty: DifficultyLevel) -> int:
        """Assign a simple mark value per difficulty."""

        if difficulty == DifficultyLevel.HARD:
            return 15
        if difficulty == DifficultyLevel.MEDIUM:
            return 10
        return 5
