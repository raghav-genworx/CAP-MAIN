"""LangGraph-powered question generation workflow using Groq."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any, Literal, cast

from langgraph.graph import END, START, StateGraph

from config.settings import Settings
from core.services.ai_gateway_service import AIGatewayService
from core.services.execution_adapter_service import ExecutionAdapterService
from schemas.question_bank import (
    DifficultyLevel,
    DifficultySource,
    MetadataStatus,
    QuestionAIDraftContext,
    QuestionAIDraftRequest,
    QuestionAIDraftResponse,
    QuestionCreateRequest,
    QuestionCreationMode,
    QuestionDraftRefinementResponse,
    QuestionGenerationSettings,
    QuestionRecord,
    QuestionStatus,
    ReferenceSolutionArtifact,
    SolutionValidationCaseResult,
    SolutionValidationReport,
    TestCase,
    ValidationStatus,
)

from ..nodes.question_nodes import QuestionAgentNodesMixin
from ..prompts.bruteforce_solution_prompt import build_bruteforce_solution_prompt
from ..prompts.question_prompts import SCOPE_NODE_SEQUENCE, SCOPE_SUMMARIES
from ..states.question_state import QuestionGenerationState, SolutionOutput

LOGGER = logging.getLogger(__name__)

FULL_NODE_SEQUENCE = [
    "orchestrator",
    "problem_statement",
    "constraints",
    "examples",
    "hidden_tests",
    "solution",
    "validation",
    "multi_language_solutions",
    "metadata",
    "duplicate_detection",
    "quality_review",
]

QC_REFINEMENT_ROUNDS = 3

NODE_LABELS = {
    "orchestrator": "Preparing request",
    "problem_statement": "Writing problem statement",
    "constraints": "Building constraints and formats",
    "examples": "Creating sample tests",
    "hidden_tests": "Creating hidden and edge tests",
    "solution": "Generating primary solution",
    "validation": "Running validation",
    "multi_language_solutions": "Generating language solutions",
    "metadata": "Classifying metadata",
    "duplicate_detection": "Checking duplicates",
    "quality_review": "Reviewing quality",
}


class QuestionGenerationWorkflow(QuestionAgentNodesMixin):
    """LangGraph workflow that coordinates question-generation agents."""

    def __init__(
        self,
        settings: Settings,
        ai_gateway: AIGatewayService,
        execution_adapter: ExecutionAdapterService,
    ) -> None:
        self._settings = settings
        self._ai_gateway = ai_gateway
        self._execution_adapter = execution_adapter
        self._current_recruiter_uid = ""
        self._current_workflow_mode = "interactive"
        self._graph = self._build_graph().compile()

    def generate(
        self,
        recruiter_uid: str,
        request: QuestionAIDraftRequest,
        existing_questions: list[QuestionRecord],
    ) -> QuestionAIDraftResponse:
        """Run scoped or full generation and return a recruiter-ready draft."""

        try:
            self._current_recruiter_uid = recruiter_uid
            self._current_workflow_mode = (
                "publish_review"
                if request.generation_scope == "full"
                else "interactive"
            )
            state = self._build_initial_state(request, existing_questions)
            if request.generation_scope == "full":
                result = cast(QuestionGenerationState, self._graph.invoke(state))
            else:
                result = self._run_scoped_generation(state, request.generation_scope)
            result = self._normalize_final_test_counts(result, request)

            return self._response_from_result(result, request)
        except Exception as exc:  # pragma: no cover
            LOGGER.error("Question generation failed: %s", exc)
            error_message = f"AI generation failed: {str(exc)}"
            return QuestionAIDraftResponse(
                draft=None,
                summary="Generation Failed",
                notes=[],
                solution_validation=None,
                error=error_message,
            )

    def refine_test_cases(
        self,
        recruiter_uid: str,
        draft: QuestionAIDraftContext,
    ) -> QuestionDraftRefinementResponse:
        """QC existing tests with a brute-force oracle and repair tests or source."""

        self._current_recruiter_uid = recruiter_uid
        self._current_workflow_mode = "interactive"
        state = self._build_refinement_state(draft, "tests")
        sample_tests = list(draft.sample_test_cases)
        hidden_tests = list(draft.hidden_test_cases)
        source_code = self._sanitize_reference_solution(draft.reference_solution)
        brute_force_source = self._generate_bruteforce_solution(state)
        repaired_count = 0
        solution_changed = False
        qc_notes: list[str] = []

        for round_number in range(1, QC_REFINEMENT_ROUNDS + 1):
            round_state = cast(
                QuestionGenerationState,
                {
                    **state,
                    "sample_test_cases": sample_tests,
                    "hidden_test_cases": hidden_tests,
                    "reference_solution": source_code,
                },
            )
            primary_report = self._validate_reference_solution(round_state)
            oracle_report = self._validate_oracle_solution(
                round_state,
                brute_force_source,
            )
            sample_tests, hidden_tests, expected_output_changes = (
                self._repair_expected_outputs_from_oracle(
                    sample_tests,
                    hidden_tests,
                    oracle_report,
                )
            )
            if expected_output_changes:
                repaired_count += expected_output_changes
                qc_notes.append(
                    (
                        f"Round {round_number}: brute-force oracle corrected "
                        f"{expected_output_changes} expected output"
                        f"{'' if expected_output_changes == 1 else 's'}."
                    ),
                )
                continue

            solution_repair_results = self._solution_repair_results_from_oracle(
                primary_report,
                oracle_report,
            )
            if solution_repair_results:
                repair_report = self._report_for_results(
                    primary_report,
                    solution_repair_results,
                )
                repair_sample_tests, repair_hidden_tests = self._tests_for_results(
                    sample_tests,
                    hidden_tests,
                    solution_repair_results,
                )
                repaired_source = self._repair_reference_solution(
                    state=round_state,
                    source_code=source_code,
                    validation_report=repair_report,
                    sample_tests=repair_sample_tests,
                    hidden_tests=repair_hidden_tests,
                    round_number=round_number,
                )
                if repaired_source.strip() != source_code.strip():
                    source_code = repaired_source
                    solution_changed = True
                    qc_notes.append(
                        (
                            f"Round {round_number}: expected output matched the "
                            "brute-force oracle, so the solution was repaired."
                        ),
                    )
                    continue

            qc_notes.append(
                f"Round {round_number}: QC found no further automatic repairs.",
            )
            break

        refined_state = cast(
            QuestionGenerationState,
            {
                **state,
                "sample_test_cases": sample_tests,
                "hidden_test_cases": hidden_tests,
                "reference_solution": source_code,
            },
        )
        final_report = self._validate_reference_solution(refined_state)
        if final_report.status == "passed" and repaired_count and solution_changed:
            summary = (
                f"QC repaired {repaired_count} expected output"
                f"{'' if repaired_count == 1 else 's'}, repaired the solution, "
                "and re-ran all tests successfully."
            )
        elif final_report.status == "passed" and repaired_count:
            summary = (
                f"QC repaired {repaired_count} expected output"
                f"{'' if repaired_count == 1 else 's'} with the brute-force "
                "oracle and re-ran all tests successfully."
            )
        elif final_report.status == "passed" and solution_changed:
            summary = (
                "QC kept expected outputs unchanged, repaired the solution using "
                "the brute-force oracle evidence, and re-ran all tests successfully."
            )
        else:
            summary = (
                "QC completed but remaining failures need recruiter review. "
                + " ".join(qc_notes[-2:])
            )
        return QuestionDraftRefinementResponse(
            draft=self._refined_draft(
                draft,
                sample_tests=sample_tests,
                hidden_tests=hidden_tests,
                reference_solution=source_code,
                report=final_report,
            ),
            validation_report=final_report,
            summary=summary,
            repaired_test_case_count=repaired_count,
            solution_changed=solution_changed,
        )

    def refine_solution(
        self,
        recruiter_uid: str,
        draft: QuestionAIDraftContext,
    ) -> QuestionDraftRefinementResponse:
        """Repair source from the problem contract, using failures as evidence."""

        self._current_recruiter_uid = recruiter_uid
        self._current_workflow_mode = "interactive"
        state = self._build_refinement_state(draft, "solution")
        initial_report = self._validate_reference_solution(state)
        sample_tests = list(draft.sample_test_cases)
        hidden_tests = list(draft.hidden_test_cases)
        source_code = self._sanitize_reference_solution(draft.reference_solution)
        repaired_source = source_code
        if initial_report.status != "passed":
            failing_sample_indexes = {
                result.index
                for result in initial_report.results
                if result.bucket == "sample" and not result.passed
            }
            failing_hidden_indexes = {
                result.index
                for result in initial_report.results
                if result.bucket == "hidden" and not result.passed
            }
            repaired_source = self._repair_reference_solution(
                state=state,
                source_code=source_code,
                validation_report=initial_report,
                sample_tests=[
                    test_case
                    for index, test_case in enumerate(sample_tests, start=1)
                    if index in failing_sample_indexes
                ],
                hidden_tests=[
                    test_case
                    for index, test_case in enumerate(hidden_tests, start=1)
                    if index in failing_hidden_indexes
                ],
                round_number=1,
            )

        solution_changed = repaired_source.strip() != source_code.strip()
        refined_state = cast(
            QuestionGenerationState,
            {**state, "reference_solution": repaired_source},
        )
        final_report = self._validate_reference_solution(refined_state)
        if initial_report.status == "passed":
            summary = "The current solution already passes all existing tests."
        elif solution_changed:
            summary = (
                "Repaired the solution from the problem statement and constraints, "
                "then re-ran all tests."
            )
        else:
            summary = "The solution could not be changed; review remaining failures."
        return QuestionDraftRefinementResponse(
            draft=self._refined_draft(
                draft,
                sample_tests=sample_tests,
                hidden_tests=hidden_tests,
                reference_solution=repaired_source,
                report=final_report,
            ),
            validation_report=final_report,
            summary=summary,
            solution_changed=solution_changed,
        )

    def _generate_bruteforce_solution(
        self,
        state: QuestionGenerationState,
    ) -> str:
        """Generate an independent correctness-first oracle for testcase QC."""

        language = self._normalize_solution_language(
            state.get("reference_language", "python"),
        )
        system_prompt, user_prompt = build_bruteforce_solution_prompt(
            state,
            language=language,
            sample_cases=[
                {"input": case.input, "is_sample": case.is_sample}
                for case in state.get("sample_test_cases", [])
            ],
            hidden_cases=[
                {"input": case.input, "is_sample": case.is_sample}
                for case in state.get("hidden_test_cases", [])
            ],
            strict_contract_guidance=self._strict_solution_contract_guidance(language),
            language_contract_guidance=self._solution_contract_guidance(language),
        )
        model = self._structured_completion(
            schema_name="bruteforce_solution",
            schema_model=SolutionOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return self._ensure_runnable_reference_solution(
            state=state,
            candidate=model.reference_solution,
            language=language,
            schema_name="bruteforce_solution_contract_retry",
            rejection_context=(
                "Brute-force oracle generation did not satisfy the runnable-code "
                "contract."
            ),
        )

    def _validate_oracle_solution(
        self,
        state: QuestionGenerationState,
        brute_force_source: str,
    ) -> SolutionValidationReport:
        """Run the brute-force oracle against the current expected outputs."""

        language = self._normalize_solution_language(
            state.get("reference_language", "python"),
        )
        return self._validate_source_against_tests(
            language=language,
            source_code=brute_force_source,
            sample_tests=self._complete_test_cases(
                state.get("sample_test_cases", []),
            ),
            hidden_tests=self._complete_test_cases(
                state.get("hidden_test_cases", []),
            ),
            rounds=[],
            time_limit_seconds=state.get("execution_time_limit_seconds"),
            memory_limit_kb=(state.get("memory_limit_mb", 256) * 1024),
        )

    def _repair_expected_outputs_from_oracle(
        self,
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
        oracle_report: SolutionValidationReport,
    ) -> tuple[list[TestCase], list[TestCase], int]:
        """Use brute-force actual output as the repaired expected output."""

        repaired_sample_tests = list(sample_tests)
        repaired_hidden_tests = list(hidden_tests)
        repaired_count = 0
        for result in oracle_report.results:
            if result.passed or not self._is_expected_output_repair_candidate(result):
                continue
            target_tests = (
                repaired_sample_tests
                if result.bucket == "sample"
                else repaired_hidden_tests
            )
            target_index = result.index - 1
            if target_index < 0 or target_index >= len(target_tests):
                continue
            original = target_tests[target_index]
            if original.expected_output == result.actual_output:
                continue
            target_tests[target_index] = original.model_copy(
                update={"expected_output": result.actual_output},
            )
            repaired_count += 1
        return repaired_sample_tests, repaired_hidden_tests, repaired_count

    @staticmethod
    def _solution_repair_results_from_oracle(
        primary_report: SolutionValidationReport,
        oracle_report: SolutionValidationReport,
    ) -> list[SolutionValidationCaseResult]:
        """Return primary failures where the brute-force oracle validates expected."""

        oracle_results = {
            (result.bucket, result.index): result
            for result in oracle_report.results
        }
        return [
            result
            for result in primary_report.results
            if not result.passed
            and oracle_results.get((result.bucket, result.index))
            and oracle_results[(result.bucket, result.index)].passed
        ]

    @staticmethod
    def _report_for_results(
        report: SolutionValidationReport,
        results: list[SolutionValidationCaseResult],
    ) -> SolutionValidationReport:
        """Create a focused validation report for solution repair prompts."""

        return report.model_copy(
            update={
                "results": results,
                "passed_count": 0,
                "failed_count": len(results),
                "summary": (
                    f"Reference solution failed {len(results)} oracle-confirmed "
                    "execution check"
                    f"{'' if len(results) == 1 else 's'}."
                ),
            },
        )

    @staticmethod
    def _tests_for_results(
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
        results: list[SolutionValidationCaseResult],
    ) -> tuple[list[TestCase], list[TestCase]]:
        """Return testcase rows that correspond to the supplied result list."""

        sample_indexes = {
            result.index
            for result in results
            if result.bucket == "sample"
        }
        hidden_indexes = {
            result.index
            for result in results
            if result.bucket == "hidden"
        }
        return (
            [
                test_case
                for index, test_case in enumerate(sample_tests, start=1)
                if index in sample_indexes
            ],
            [
                test_case
                for index, test_case in enumerate(hidden_tests, start=1)
                if index in hidden_indexes
            ],
        )

    def _build_refinement_state(
        self,
        draft: QuestionAIDraftContext,
        scope: Literal["tests", "solution"],
    ) -> QuestionGenerationState:
        """Build normal agent state while preserving the complete current draft."""

        request = QuestionAIDraftRequest(
            prompt=(
                "Refine the existing draft using execution evidence while preserving "
                "the authoritative problem contract."
            ),
            generation_scope=scope,
            reference_language=draft.reference_language,
            title_hint=draft.title or None,
            focus_tags=draft.tags,
            current_draft=draft,
            generation_settings=QuestionGenerationSettings(
                topics=draft.topics,
                supported_languages=draft.supported_languages,
                candidate_solve_time_minutes=draft.candidate_solve_time_minutes,
                time_limit_minutes=draft.candidate_solve_time_minutes,
                execution_time_limit_seconds=draft.execution_time_limit_seconds,
                memory_limit_mb=draft.memory_limit_mb,
                sample_test_case_count=min(
                    10,
                    max(1, len(draft.sample_test_cases)),
                ),
                hidden_test_case_count=min(
                    50,
                    max(1, len(draft.hidden_test_cases)),
                ),
            ),
        )
        return self._build_initial_state(request, [])

    @staticmethod
    def _count_expected_output_changes(
        before: list[TestCase],
        after: list[TestCase],
    ) -> int:
        return sum(
            1
            for old, new in zip(before, after, strict=False)
            if old.expected_output != new.expected_output
        )

    @staticmethod
    def _refined_draft(
        draft: QuestionAIDraftContext,
        *,
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
        reference_solution: str,
        report: SolutionValidationReport,
    ) -> QuestionCreateRequest:
        payload = draft.model_dump()
        primary_language = QuestionGenerationWorkflow._normalize_solution_language(
            draft.reference_language,
        )
        reference_solutions = dict(draft.reference_solutions)
        if reference_solution.strip():
            reference_solutions[primary_language] = ReferenceSolutionArtifact(
                language=primary_language,
                source_code=reference_solution,
                validation_status=ValidationStatus(report.status),
                time_complexity=draft.time_complexity,
                space_complexity=draft.space_complexity,
            )
        payload.update(
            {
                "sample_test_cases": sample_tests,
                "hidden_test_cases": hidden_tests,
                "reference_solution": reference_solution,
                "reference_solutions": reference_solutions,
                "validation_report": report,
                "validation_status": report.status,
                "validation_updated_at": datetime.now(UTC),
                "creation_mode": QuestionCreationMode.AI_ASSISTED,
            }
        )
        return QuestionCreateRequest.model_validate(payload)

    def generate_events(
        self,
        recruiter_uid: str,
        request: QuestionAIDraftRequest,
        existing_questions: list[QuestionRecord],
    ) -> Iterator[dict[str, Any]]:
        """Run generation and yield graph movement progress events."""

        try:
            self._current_recruiter_uid = recruiter_uid
            self._current_workflow_mode = (
                "publish_review"
                if request.generation_scope == "full"
                else "interactive"
            )
            state = self._build_initial_state(request, existing_questions)
            node_sequence = (
                FULL_NODE_SEQUENCE
                if request.generation_scope == "full"
                else [
                    "orchestrator",
                    *SCOPE_NODE_SEQUENCE.get(request.generation_scope, []),
                ]
            )
            result = state
            total = max(len(node_sequence), 1)
            yield {
                "type": "start",
                "scope": request.generation_scope,
                "message": "Question agent started.",
                "current_node": None,
                "next_node": node_sequence[0] if node_sequence else None,
                "progress": 0,
            }
            for index, node_name in enumerate(node_sequence, start=1):
                previous_node = node_sequence[index - 2] if index > 1 else "START"
                yield {
                    "type": "edge",
                    "scope": request.generation_scope,
                    "message": f"{previous_node} -> {node_name}",
                    "current_node": previous_node,
                    "next_node": node_name,
                    "progress": round(((index - 1) / total) * 100),
                }
                yield {
                    "type": "node_start",
                    "scope": request.generation_scope,
                    "message": NODE_LABELS.get(
                        node_name,
                        node_name.replace("_", " ").title(),
                    ),
                    "current_node": node_name,
                    "next_node": None,
                    "progress": round(((index - 1) / total) * 100),
                }
                result = self._merge_state(result, self._node_runner(node_name)(result))
                yield {
                    "type": "node_complete",
                    "scope": request.generation_scope,
                    "message": f"{NODE_LABELS.get(node_name, node_name)} complete.",
                    "current_node": node_name,
                    "next_node": node_sequence[index] if index < total else "END",
                    "progress": round((index / total) * 100),
                }

            result["summary"] = SCOPE_SUMMARIES.get(
                request.generation_scope,
                "Generated content from your description.",
            )
            result = self._normalize_final_test_counts(result, request)
            yield {
                "type": "complete",
                "scope": request.generation_scope,
                "message": "Question agent completed.",
                "current_node": node_sequence[-1] if node_sequence else None,
                "next_node": "END",
                "progress": 100,
                "response": self._response_from_result(result, request).model_dump(
                    mode="json",
                ),
            }
        except Exception as exc:  # pragma: no cover
            LOGGER.error("Question generation stream failed: %s", exc)
            yield {
                "type": "error",
                "scope": request.generation_scope,
                "message": f"AI generation failed: {str(exc)}",
                "progress": 100,
            }

    def _build_initial_state(
        self,
        request: QuestionAIDraftRequest,
        existing_questions: list[QuestionRecord],
    ) -> QuestionGenerationState:
        """Normalize request context for one generation run."""

        current_draft = request.current_draft
        title_hint = (
            request.title_hint.strip()
            if request.title_hint
            else (current_draft.title.strip() if current_draft else "")
        )
        focus_tags = self._normalize_tokens(
            request.focus_tags or (current_draft.tags if current_draft else [])
        )
        settings = request.generation_settings
        state: QuestionGenerationState = {
            "prompt": request.prompt.strip(),
            "generation_scope": request.generation_scope,
            "difficulty_hint": "",
            "title_hint": title_hint,
            "focus_tags": focus_tags,
            "reference_language": (
                request.reference_language.strip()
                or (current_draft.reference_language if current_draft else "")
                or "python"
            ),
            "generation_settings": settings,
            "existing_question_titles": [
                question.title.strip()
                for question in existing_questions
                if question.title
            ],
            "existing_question_tags": [
                tag
                for question in existing_questions
                for tag in self._normalize_tokens(question.tags)
            ],
            "question_count": settings.question_count,
            "candidate_solve_time_minutes": settings.candidate_solve_time_minutes
            or settings.time_limit_minutes,
            "execution_time_limit_seconds": settings.execution_time_limit_seconds,
            "memory_limit_mb": settings.memory_limit_mb,
            "metadata_status": MetadataStatus.PENDING.value,
            "difficulty_source": DifficultySource.LEGACY.value,
            "notes": [
                "Question orchestrator received the recruiter description.",
                (
                    "Single-question mode is active; generation settings asking for "
                    f"{settings.question_count} question(s) will be "
                    "collapsed into one draft."
                    if settings.question_count > 1
                    else "Single-question mode confirmed."
                ),
            ],
            "execution_history": ["Orchestrator: request normalized"],
        }
        if title_hint:
            state["title"] = title_hint
        if current_draft:
            if current_draft.problem_statement.strip():
                state["problem_statement"] = current_draft.problem_statement.strip()
            if current_draft.constraints.strip():
                state["constraints"] = current_draft.constraints.strip()
            if current_draft.input_format.strip():
                state["input_format"] = current_draft.input_format.strip()
            if current_draft.input_explanation.strip():
                state["input_explanation"] = current_draft.input_explanation.strip()
            if current_draft.output_format.strip():
                state["output_format"] = current_draft.output_format.strip()
            if current_draft.output_explanation.strip():
                state["output_explanation"] = current_draft.output_explanation.strip()
            if current_draft.topics:
                state["topics"] = self._normalize_tokens(current_draft.topics)
            if current_draft.tags:
                state["tags"] = self._normalize_tokens(current_draft.tags)
            if current_draft.category.strip():
                state["category"] = current_draft.category.strip().lower()
            if current_draft.sample_test_cases:
                state["sample_test_cases"] = current_draft.sample_test_cases
            if current_draft.hidden_test_cases:
                state["hidden_test_cases"] = current_draft.hidden_test_cases
            if current_draft.reference_solution.strip():
                state["reference_solution"] = current_draft.reference_solution.strip()
            if current_draft.reference_solutions:
                state["reference_solutions"] = current_draft.reference_solutions
            if current_draft.solution_approach.strip():
                state["solution_approach"] = current_draft.solution_approach.strip()
            if current_draft.time_complexity.strip():
                state["time_complexity"] = current_draft.time_complexity.strip()
            if current_draft.space_complexity.strip():
                state["space_complexity"] = current_draft.space_complexity.strip()
            state["candidate_solve_time_minutes"] = (
                current_draft.candidate_solve_time_minutes
            )
            state["execution_time_limit_seconds"] = (
                current_draft.execution_time_limit_seconds
            )
            state["memory_limit_mb"] = current_draft.memory_limit_mb
            state["metadata_status"] = current_draft.metadata_status.value
            state["difficulty_source"] = current_draft.difficulty_source.value
            state["validation_status"] = current_draft.validation_status.value
            if current_draft.validation_report:
                state["solution_validation"] = current_draft.validation_report
            if current_draft.supported_languages:
                state["supported_languages"] = self._normalize_languages(
                    current_draft.supported_languages,
                    current_draft.reference_language,
                    request.generation_settings.supported_languages,
                )
        return state

    def _run_scoped_generation(
        self,
        state: QuestionGenerationState,
        scope: str,
    ) -> QuestionGenerationState:
        """Run only the agents needed for one builder section."""

        result = self._merge_state(state, self._orchestrator_node(state))
        for node_name in SCOPE_NODE_SEQUENCE.get(scope, []):
            runner = self._node_runner(node_name)
            result = self._merge_state(result, runner(result))

        result["summary"] = SCOPE_SUMMARIES.get(
            scope,
            "Generated content from your description.",
        )
        return result

    def _node_runner(
        self,
        node_name: str,
    ) -> Callable[[QuestionGenerationState], QuestionGenerationState]:
        node_runners = {
            "orchestrator": self._orchestrator_node,
            "problem_statement": self._problem_statement_node,
            "metadata": self._metadata_node,
            "constraints": self._constraint_node,
            "examples": self._example_node,
            "hidden_tests": self._hidden_test_node,
            "solution": self._solution_node,
            "validation": self._validation_node,
            "multi_language_solutions": self._multi_language_solution_node,
            "duplicate_detection": self._duplicate_detection_node,
            "quality_review": self._quality_review_node,
        }
        return node_runners[node_name]

    def _response_from_result(
        self,
        result: QuestionGenerationState,
        request: QuestionAIDraftRequest,
    ) -> QuestionAIDraftResponse:
        draft = self._build_draft_from_state(result, request)
        notes = self._append_notes(
            result.get("notes", []),
            result.get("summary", ""),
        )
        execution_history = result.get("execution_history", [])
        notes.extend(
            [
                "AI-drafted content is ready for recruiter review.",
                "Please verify sample and hidden test cases before publishing.",
                f"Generation scope: {request.generation_scope}.",
            ],
        )
        notes.extend(execution_history[:2])

        return QuestionAIDraftResponse(
            draft=draft,
            summary=result.get(
                "summary",
                SCOPE_SUMMARIES.get(
                    request.generation_scope,
                    "Generated content from your description.",
                ),
            ),
            notes=notes,
            solution_validation=result.get("solution_validation"),
        )

    def _normalize_final_test_counts(
        self,
        result: QuestionGenerationState,
        request: QuestionAIDraftRequest,
    ) -> QuestionGenerationState:
        """Keep generated testcase counts aligned with recruiter settings."""

        count_scopes = {
            "full",
            "examples",
            "tests",
            "tests_solution",
            "solution",
        }
        if request.generation_scope not in count_scopes:
            return result

        settings = request.generation_settings
        current_draft = request.current_draft
        sample_cases = [
            case.model_copy(update={"is_sample": True})
            for case in self._complete_test_cases(result.get("sample_test_cases", []))
        ]
        hidden_cases = [
            case.model_copy(update={"is_sample": False})
            for case in self._complete_test_cases(result.get("hidden_test_cases", []))
        ]
        if current_draft:
            sample_cases = self._merge_unique_test_cases(
                sample_cases,
                [
                    case.model_copy(update={"is_sample": True})
                    for case in self._complete_test_cases(
                        current_draft.sample_test_cases,
                    )
                ],
            )
            hidden_cases = self._merge_unique_test_cases(
                hidden_cases,
                [
                    case.model_copy(update={"is_sample": False})
                    for case in self._complete_test_cases(
                        current_draft.hidden_test_cases,
                    )
                ],
            )

        target_sample_count = max(1, settings.sample_test_case_count)
        target_hidden_count = max(1, settings.hidden_test_case_count)
        sample_cases = sample_cases[:target_sample_count]
        hidden_cases = hidden_cases[:target_hidden_count]

        notes = list(result.get("notes", []))
        if (
            len(sample_cases) == target_sample_count
            and len(hidden_cases) == target_hidden_count
        ):
            notes.append(
                (
                    "Exact testcase count verified: "
                    f"{target_sample_count} sample and {target_hidden_count} hidden."
                ),
            )
        else:
            notes.append(
                (
                    "Testcase count needs recruiter review: generated "
                    f"{len(sample_cases)}/{target_sample_count} sample and "
                    f"{len(hidden_cases)}/{target_hidden_count} hidden after "
                    "constraint filtering."
                ),
            )

        normalized = dict(result)
        normalized["sample_test_cases"] = sample_cases
        normalized["hidden_test_cases"] = hidden_cases
        normalized["notes"] = notes
        return cast(QuestionGenerationState, normalized)

    def _build_draft_from_state(
        self,
        result: QuestionGenerationState,
        request: QuestionAIDraftRequest,
    ) -> QuestionCreateRequest:
        """Map graph state into a draft payload with safe defaults."""

        settings = request.generation_settings
        difficulty_value = result.get("difficulty") or (
            request.difficulty.value
            if request.difficulty
            else DifficultyLevel.MEDIUM.value
        )
        supported_languages = (
            result.get("supported_languages") or settings.supported_languages
        )
        return QuestionCreateRequest(
            title=result.get("title") or request.title_hint or "Untitled Question",
            problem_statement=result.get("problem_statement", ""),
            difficulty=DifficultyLevel(difficulty_value),
            topics=result.get("topics", []),
            tags=result.get("tags", []),
            category=result.get("category", ""),
            constraints=result.get("constraints", ""),
            input_format=result.get("input_format", ""),
            input_explanation=result.get("input_explanation", ""),
            output_format=result.get("output_format", ""),
            output_explanation=result.get("output_explanation", ""),
            sample_test_cases=[
                case.model_copy(update={"is_sample": True})
                for case in result.get("sample_test_cases", [])
            ],
            hidden_test_cases=[
                case.model_copy(update={"is_sample": False})
                for case in result.get("hidden_test_cases", [])
            ],
            reference_solution=result.get("reference_solution", ""),
            reference_language=request.reference_language.strip() or "python",
            supported_languages=supported_languages,
            candidate_solve_time_minutes=result.get(
                "candidate_solve_time_minutes",
                settings.candidate_solve_time_minutes or settings.time_limit_minutes,
            ),
            execution_time_limit_seconds=result.get(
                "execution_time_limit_seconds",
                settings.execution_time_limit_seconds,
            ),
            memory_limit_mb=result.get("memory_limit_mb", settings.memory_limit_mb),
            metadata_status=MetadataStatus(
                result.get("metadata_status", MetadataStatus.PENDING.value),
            ),
            difficulty_source=DifficultySource(
                result.get("difficulty_source", DifficultySource.LEGACY.value),
            ),
            validation_report=result.get("solution_validation"),
            validation_status=ValidationStatus(
                result.get("validation_status", ValidationStatus.NOT_RUN.value),
            ),
            reference_solutions=result.get("reference_solutions", {}),
            solution_approach=result.get("solution_approach", ""),
            time_complexity=result.get("time_complexity", ""),
            space_complexity=result.get("space_complexity", ""),
            status=QuestionStatus.DRAFT,
            creation_mode=QuestionCreationMode.AI_ASSISTED,
        )

    @staticmethod
    def _merge_state(
        state: QuestionGenerationState,
        patch: QuestionGenerationState,
    ) -> QuestionGenerationState:
        merged = dict(state)
        merged.update(patch)
        return cast(QuestionGenerationState, merged)

    def _build_graph(self) -> StateGraph[QuestionGenerationState]:
        graph: StateGraph[QuestionGenerationState] = StateGraph(QuestionGenerationState)
        graph.add_node("orchestrator", self._orchestrator_node)
        graph.add_node("problem_statement", self._problem_statement_node)
        graph.add_node("metadata", self._metadata_node)
        graph.add_node("constraints", self._constraint_node)
        graph.add_node("examples", self._example_node)
        graph.add_node("hidden_tests", self._hidden_test_node)
        graph.add_node("solution", self._solution_node)
        graph.add_node("validation", self._validation_node)
        graph.add_node("multi_language_solutions", self._multi_language_solution_node)
        graph.add_node("duplicate_detection", self._duplicate_detection_node)
        graph.add_node("quality_review", self._quality_review_node)

        graph.add_edge(START, "orchestrator")
        graph.add_edge("orchestrator", "problem_statement")
        graph.add_edge("problem_statement", "constraints")
        graph.add_edge("constraints", "examples")
        graph.add_edge("examples", "hidden_tests")
        graph.add_edge("hidden_tests", "solution")
        graph.add_edge("solution", "validation")
        graph.add_edge("validation", "multi_language_solutions")
        graph.add_edge("multi_language_solutions", "metadata")
        graph.add_edge("metadata", "duplicate_detection")
        graph.add_edge("duplicate_detection", "quality_review")
        graph.add_edge("quality_review", END)
        return graph


__all__ = ["QuestionGenerationWorkflow"]
