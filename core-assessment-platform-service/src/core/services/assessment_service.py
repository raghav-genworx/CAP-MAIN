"""Recruiter assessment management and candidate portal workflows."""

from __future__ import annotations

import logging
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from random import Random
from secrets import token_urlsafe
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config.settings import Settings, get_settings
from core.exceptions.assessment import (
    AssessmentNotFoundError,
    AssessmentStoreUnavailableError,
    AssessmentValidationError,
    CandidateInviteError,
    EvaluationAdapterError,
    EvaluationResourceNotFoundError,
    ExecutionAdapterError,
)
from core.services.assessment_lifecycle import (
    assessment_status_from_slots,
    effective_slot_status,
    slot_record_from_model,
    slot_summary_from_model,
    submitted_assignment_count,
)
from core.services.assessment_policy import (
    allocate_template_marks,
    default_language,
    normalize_languages,
    validate_scoring_weights,
)
from core.services.assessment_schedule import normalize_assessment_schedule
from core.services.candidate_csv_import import parse_candidate_csv
from core.services.candidate_execution_policy import (
    HIDDEN_CHECK_COOLDOWN_SECONDS,
    can_execute_final_submission,
    complete_test_cases,
    execution_failed_results,
    hidden_check_cooldown_remaining,
    hidden_error_type,
    not_attempted_results,
    time_remaining_seconds,
)
from core.services.candidate_session_service import CandidateSessionService
from core.services.evaluation_payload_builder import build_evaluation_payload
from core.services.notification_service import NotificationService
from core.services.output_validation import (
    apply_answer_validation,
    default_checker_explanation,
    normalize_answer_validation_mode,
)
from data.models.postgres.assessment_question import AssessmentQuestionModel
from data.models.postgres.assessment_slot import AssessmentSlotModel
from data.models.postgres.assessment_template import AssessmentTemplateModel
from data.models.postgres.candidate import CandidateModel
from data.models.postgres.candidate_assessment import CandidateAssessmentModel
from data.models.postgres.candidate_proctor_event import CandidateProctorEventModel
from data.models.postgres.question_bank_question import QuestionBankQuestionModel
from data.models.postgres.submission import SubmissionModel
from data.repositories.assessment_repository import AssessmentRepository
from handlers.http_clients.brevo import InviteMailService
from handlers.http_clients.evaluation import (
    EvaluationAdapterService,
    EvaluationReportDownload,
)
from handlers.http_clients.execution import ExecutionAdapterService
from schemas.assessments import (
    AssessmentCreateRequest,
    AssessmentListResponse,
    AssessmentQuestionAssignRequest,
    AssessmentQuestionRecord,
    AssessmentRecord,
    AssessmentSlotActionRequest,
    AssessmentSlotCreateRequest,
    AssessmentSlotListResponse,
    AssessmentSlotRecord,
    AssessmentSlotUpdateRequest,
    AssessmentStatus,
    AssessmentUpdateRequest,
    CandidateAssessmentStatus,
    CandidateCSVImportRequest,
    CandidateImportResponse,
    EvaluationBackfillCandidateResult,
    EvaluationBackfillRequest,
    EvaluationBackfillResponse,
    ExecutionCaseResult,
    HiddenCheckResponse,
    HiddenExecutionCaseResult,
    HiddenFeedbackMode,
    InviteDispatchResponse,
    InviteEmailStatus,
    MonitoringCandidateRecord,
    MonitoringResponse,
    SampleRunResponse,
    SlotCandidateListResponse,
    SlotCandidateRecord,
    SlotStatus,
    SubmissionExecutionSummary,
    SubmissionStatus,
)
from schemas.candidate_portal import (
    CandidateAssessmentPortalResponse,
    CandidateCheckpointRequest,
    CandidateCheckpointResponse,
    CandidateCodeRunRequest,
    CandidateInviteVerificationResponse,
    CandidateProctorEventRequest,
    CandidateProctorEventResponse,
    CandidateQuestionDraftRecord,
    CandidateQuestionRecord,
    CandidateSessionClaims,
    CandidateStartResponse,
    CandidateSubmitRequest,
    CandidateSubmitResponse,
)
from schemas.evaluation_reports import (
    AssessmentEvaluationDashboard,
    AssessmentEvaluationOverview,
    AssessmentReportResponse,
    CandidateBenchmarkContext,
    CandidateEvaluationSummary,
    CandidateReportResponse,
    EvaluationJobResponse,
    RetryEvaluationResponse,
)
from schemas.question_bank import (
    AnswerValidationMode,
    DifficultyLevel,
    QuestionStatus,
    TestCase,
)

logger = logging.getLogger(__name__)


@dataclass
class CandidateAssessmentContext:
    """Loaded context for one candidate assessment session."""

    assessment: AssessmentTemplateModel
    slot: AssessmentSlotModel
    candidate: CandidateModel
    candidate_assessment: CandidateAssessmentModel
    questions: list[QuestionBankQuestionModel]
    mappings: list[AssessmentQuestionModel]
    submissions: dict[str, SubmissionModel]


@dataclass(frozen=True)
class DeliveredQuestionMapping:
    """Candidate-specific view of a pool mapping with template-slot marks."""

    question_id: str
    question_order: int
    marks: int
    is_mandatory: bool


class AssessmentService:
    """Manage recruiter assessments and candidate test sessions."""

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self._repository = AssessmentRepository(session)
        self._settings = settings or get_settings()
        self._candidate_session_service = CandidateSessionService(self._settings)
        self._execution_adapter = ExecutionAdapterService(self._settings)
        self._evaluation_adapter = EvaluationAdapterService(self._settings)
        self._invite_mail_service = InviteMailService(self._settings)
        self._notification_service = NotificationService(session, self._settings)

    def list_assessments(self, recruiter_uid: str) -> AssessmentListResponse:
        """Return recruiter-owned assessment templates."""

        try:
            items = self._repository.list_assessments(recruiter_uid)
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError("Unable to read assessments") from exc
        records = [
            self._assessment_record_from_model(item, recruiter_uid) for item in items
        ]
        return AssessmentListResponse(items=records, total=len(records))

    def create_assessment(
        self,
        recruiter_uid: str,
        payload: AssessmentCreateRequest,
    ) -> AssessmentRecord:
        """Create a recruiter-owned assessment template."""

        validate_scoring_weights(
            payload.test_case_score_weight,
            payload.coding_score_weight,
            payload.ai_score_weight,
        )
        model = AssessmentTemplateModel(
            recruiter_uid=recruiter_uid,
            title=payload.title.strip(),
            description=payload.description.strip(),
            instructions=payload.instructions.strip(),
            duration_minutes=payload.duration_minutes,
            passing_score=payload.passing_score,
            test_case_score_weight=payload.test_case_score_weight,
            coding_score_weight=payload.coding_score_weight,
            ai_score_weight=payload.ai_score_weight,
            allow_resume=payload.allow_resume,
            shuffle_questions=payload.shuffle_questions,
            question_count_per_candidate=payload.question_count_per_candidate,
            difficulty_blueprint=[item.value for item in payload.difficulty_blueprint],
            show_score_to_candidate=payload.show_score_to_candidate,
            proctoring_mode=payload.proctoring_mode.strip().lower(),
            hidden_feedback_mode=payload.hidden_feedback_mode.value,
            max_hidden_checks=0,
            hidden_check_cooldown_seconds=HIDDEN_CHECK_COOLDOWN_SECONDS,
            supported_languages=normalize_languages(payload.supported_languages),
            status=(
                AssessmentStatus.ARCHIVED.value
                if payload.status == AssessmentStatus.ARCHIVED
                else AssessmentStatus.AVAILABLE.value
            ),
        )
        try:
            self._repository.add(model)
            self._repository.commit()
            self._repository.refresh(model)
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise AssessmentStoreUnavailableError(
                "Unable to create assessment"
            ) from exc
        return self._assessment_record_from_model(model, recruiter_uid)

    def update_assessment(
        self,
        recruiter_uid: str,
        assessment_id: str,
        payload: AssessmentUpdateRequest,
    ) -> AssessmentRecord:
        """Patch an assessment template."""

        model = self._get_assessment(recruiter_uid, assessment_id)
        if model is None:
            raise AssessmentNotFoundError()

        updates = payload.model_dump(exclude_unset=True)
        if "title" in updates and payload.title is not None:
            model.title = payload.title.strip()
        if "description" in updates and payload.description is not None:
            model.description = payload.description.strip()
        if "instructions" in updates and payload.instructions is not None:
            model.instructions = payload.instructions.strip()
        if payload.duration_minutes is not None:
            model.duration_minutes = payload.duration_minutes
        if payload.passing_score is not None:
            model.passing_score = payload.passing_score
        if payload.test_case_score_weight is not None:
            model.test_case_score_weight = payload.test_case_score_weight
        if payload.coding_score_weight is not None:
            model.coding_score_weight = payload.coding_score_weight
        if payload.ai_score_weight is not None:
            model.ai_score_weight = payload.ai_score_weight
        if payload.allow_resume is not None:
            model.allow_resume = payload.allow_resume
        if payload.shuffle_questions is not None:
            model.shuffle_questions = payload.shuffle_questions
        if payload.question_count_per_candidate is not None:
            model.question_count_per_candidate = payload.question_count_per_candidate
        if payload.difficulty_blueprint is not None:
            model.difficulty_blueprint = [
                item.value for item in payload.difficulty_blueprint
            ]
        if payload.show_score_to_candidate is not None:
            model.show_score_to_candidate = payload.show_score_to_candidate
        if payload.proctoring_mode is not None:
            model.proctoring_mode = payload.proctoring_mode.strip().lower()
        if payload.hidden_feedback_mode is not None:
            model.hidden_feedback_mode = payload.hidden_feedback_mode.value
        model.max_hidden_checks = 0
        model.hidden_check_cooldown_seconds = HIDDEN_CHECK_COOLDOWN_SECONDS
        if payload.supported_languages is not None:
            proposed_languages = normalize_languages(payload.supported_languages)
            mappings = self._assessment_mappings(model.id)
            if mappings:
                records = self._question_bank_records(
                    recruiter_uid,
                    [item.question_id for item in mappings],
                )
                self._assert_assessment_language_coverage(
                    proposed_languages,
                    records,
                )
            model.supported_languages = proposed_languages
        if payload.status is not None:
            model.status = (
                AssessmentStatus.ARCHIVED.value
                if payload.status == AssessmentStatus.ARCHIVED
                else AssessmentStatus.AVAILABLE.value
            )
        validate_scoring_weights(
            model.test_case_score_weight,
            model.coding_score_weight,
            model.ai_score_weight,
        )

        try:
            self._repository.commit()
            self._repository.refresh(model)
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise AssessmentStoreUnavailableError(
                "Unable to update assessment"
            ) from exc
        return self._assessment_record_from_model(model, recruiter_uid)

    def delete_assessment(self, recruiter_uid: str, assessment_id: str) -> None:
        """Permanently delete a recruiter-owned assessment template."""

        model = self._get_assessment(recruiter_uid, assessment_id)
        if model is None:
            raise AssessmentNotFoundError()

        try:
            self._repository.delete(model)
            self._repository.commit()
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise AssessmentStoreUnavailableError(
                "Unable to delete assessment"
            ) from exc

    def set_assessment_questions(
        self,
        recruiter_uid: str,
        assessment_id: str,
        payload: AssessmentQuestionAssignRequest,
    ) -> AssessmentRecord:
        """Replace the assessment question set."""

        assessment = self._get_assessment(recruiter_uid, assessment_id)
        if assessment is None:
            raise AssessmentNotFoundError()

        normalized = self._validate_assessment_questions(
            recruiter_uid, assessment, payload.questions
        )

        try:
            self._repository.replace_assessment_questions(
                assessment_id=assessment_id,
                questions=[
                    AssessmentQuestionModel(
                        assessment_id=assessment_id,
                        question_id=normalized_item["question_id"],
                        question_order=normalized_item["question_order"],
                        marks=normalized_item["marks"],
                        is_mandatory=normalized_item["is_mandatory"],
                    )
                    for normalized_item in normalized
                ],
            )
            self._repository.commit()
            self._repository.refresh(assessment)
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise AssessmentStoreUnavailableError(
                "Unable to update assessment questions"
            ) from exc

        return self._assessment_record_from_model(assessment, recruiter_uid)

    def create_slot(
        self,
        recruiter_uid: str,
        assessment_id: str,
        payload: AssessmentSlotCreateRequest,
    ) -> AssessmentSlotRecord:
        """Create one test slot from an assessment template."""

        assessment = self._get_assessment(recruiter_uid, assessment_id)
        if assessment is None:
            raise AssessmentNotFoundError()
        schedule = normalize_assessment_schedule(
            start_at=payload.start_at,
            end_at=payload.end_at,
            timezone_name=payload.timezone_name,
            duration_minutes=payload.duration_minutes,
            reject_past_start=True,
        )

        model = AssessmentSlotModel(
            assessment_id=assessment_id,
            recruiter_uid=recruiter_uid,
            title=payload.title.strip(),
            instructions_override=payload.instructions_override.strip(),
            start_at=schedule.start_at,
            end_at=schedule.end_at,
            duration_minutes=payload.duration_minutes,
            timezone_name=schedule.timezone_name,
            timezone_offset_minutes=schedule.timezone_offset_minutes,
            status=payload.status.value,
        )
        try:
            self._repository.add(model)
            self._repository.commit()
            self._repository.refresh(model)
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise AssessmentStoreUnavailableError("Unable to create slot") from exc
        return slot_record_from_model(model, submitted_count=0, candidate_count=0)

    def update_slot(
        self,
        recruiter_uid: str,
        slot_id: str,
        payload: AssessmentSlotUpdateRequest,
    ) -> AssessmentSlotRecord:
        """Patch a scheduled test slot."""

        slot = self._get_slot(recruiter_uid, slot_id)
        if slot is None:
            raise AssessmentNotFoundError("Assessment slot not found")

        schedule = normalize_assessment_schedule(
            start_at=payload.start_at
            if payload.start_at is not None
            else slot.start_at,
            end_at=payload.end_at if payload.end_at is not None else slot.end_at,
            timezone_name=(
                payload.timezone_name
                if payload.timezone_name is not None
                else slot.timezone_name
            ),
            duration_minutes=(
                payload.duration_minutes
                if payload.duration_minutes is not None
                else slot.duration_minutes
            ),
            reject_past_start=False,
        )

        if payload.title is not None:
            slot.title = payload.title.strip()
        slot.start_at = schedule.start_at
        slot.end_at = schedule.end_at
        if payload.duration_minutes is not None:
            slot.duration_minutes = payload.duration_minutes
        slot.timezone_name = schedule.timezone_name
        slot.timezone_offset_minutes = schedule.timezone_offset_minutes
        if payload.instructions_override is not None:
            slot.instructions_override = payload.instructions_override.strip()
        if payload.status is not None:
            slot.status = payload.status.value
        try:
            self._repository.commit()
            self._repository.refresh(slot)
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise AssessmentStoreUnavailableError("Unable to update slot") from exc

        assignments = self._slot_assignment_models(recruiter_uid, slot_id)
        return slot_record_from_model(
            slot,
            submitted_count=submitted_assignment_count(assignments),
            candidate_count=len(assignments),
        )

    def control_slot(
        self,
        recruiter_uid: str,
        slot_id: str,
        payload: AssessmentSlotActionRequest,
    ) -> AssessmentSlotRecord:
        """Pause, continue, extend, or close a test slot."""

        slot = self._get_slot(recruiter_uid, slot_id)
        if slot is None:
            raise AssessmentNotFoundError("Assessment slot not found")

        now = datetime.now(UTC)
        assignments = self._slot_assignment_models(recruiter_uid, slot_id)
        if payload.action == "pause":
            if slot.status == SlotStatus.CLOSED.value:
                raise AssessmentValidationError("Closed tests cannot be paused")
            if slot.status != SlotStatus.PAUSED.value:
                slot.status = SlotStatus.PAUSED.value
                slot.paused_at = now
        elif payload.action == "continue":
            if slot.status != SlotStatus.PAUSED.value:
                raise AssessmentValidationError("Only paused tests can be continued")
            paused_at = slot.paused_at.astimezone(UTC) if slot.paused_at else now
            paused_delta = max(0, int((now - paused_at).total_seconds()))
            slot.status = SlotStatus.SCHEDULED.value
            slot.paused_at = None
            slot.total_paused_seconds = (slot.total_paused_seconds or 0) + paused_delta
            slot.end_at = slot.end_at.astimezone(UTC) + timedelta(seconds=paused_delta)
            for assignment in assignments:
                if assignment.deadline_at and assignment.status not in {
                    CandidateAssessmentStatus.SUBMITTED.value,
                    CandidateAssessmentStatus.AUTO_SUBMITTED.value,
                    CandidateAssessmentStatus.REVOKED.value,
                }:
                    assignment.deadline_at = assignment.deadline_at.astimezone(
                        UTC
                    ) + timedelta(
                        seconds=paused_delta,
                    )
        elif payload.action == "extend":
            if effective_slot_status(slot, now=now) == SlotStatus.CLOSED:
                raise AssessmentValidationError("Closed tests cannot be extended")
            if payload.extend_minutes <= 0:
                raise AssessmentValidationError(
                    "Enter extension minutes greater than zero"
                )
            extension = timedelta(minutes=payload.extend_minutes)
            slot.end_at = slot.end_at.astimezone(UTC) + extension
            for assignment in assignments:
                if assignment.deadline_at and assignment.status not in {
                    CandidateAssessmentStatus.SUBMITTED.value,
                    CandidateAssessmentStatus.AUTO_SUBMITTED.value,
                    CandidateAssessmentStatus.REVOKED.value,
                }:
                    assignment.deadline_at = (
                        assignment.deadline_at.astimezone(UTC) + extension
                    )
        elif payload.action == "close":
            slot.status = SlotStatus.CLOSED.value
            if now > slot.start_at.astimezone(UTC):
                slot.end_at = min(slot.end_at.astimezone(UTC), now)
            for assignment in assignments:
                if assignment.status != CandidateAssessmentStatus.IN_PROGRESS.value:
                    continue
                self.submit_assessment(
                    CandidateSessionClaims(
                        candidate_assessment_id=assignment.id,
                        assessment_id=assignment.assessment_id,
                        slot_id=assignment.slot_id,
                        candidate_id=assignment.candidate_id,
                        exp=int(now.timestamp()) + 60,
                    ),
                    CandidateSubmitRequest(
                        answers=[],
                        auto_submit=True,
                        submission_tag="slot_closed",
                        submission_message=(
                            "Assessment auto-submitted because the recruiter closed "
                            "the test slot."
                        ),
                    ),
                    auto_submit=True,
                )
        else:
            raise AssessmentValidationError("Unsupported slot action")

        if slot.end_at <= slot.start_at:
            raise AssessmentValidationError(
                "Slot end time must be after the start time"
            )

        try:
            self._repository.commit()
            self._repository.refresh(slot)
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise AssessmentStoreUnavailableError(
                "Unable to update slot state"
            ) from exc

        return slot_record_from_model(
            slot,
            submitted_count=submitted_assignment_count(assignments),
            candidate_count=len(assignments),
        )

    def list_slots(
        self, recruiter_uid: str, assessment_id: str
    ) -> AssessmentSlotListResponse:
        """Return all slots for an assessment template."""

        assessment = self._get_assessment(recruiter_uid, assessment_id)
        if assessment is None:
            raise AssessmentNotFoundError()

        try:
            slots = self._repository.list_slots_for_assessment(
                recruiter_uid=recruiter_uid,
                assessment_id=assessment_id,
                descending=True,
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError("Unable to read slots") from exc

        candidate_assessments = self._candidate_assessments_for_slot_ids(
            [slot.id for slot in slots]
        )
        records = []
        for slot in slots:
            assignments = candidate_assessments.get(slot.id, [])
            records.append(
                slot_record_from_model(
                    slot,
                    submitted_count=submitted_assignment_count(assignments),
                    candidate_count=len(assignments),
                )
            )
        return AssessmentSlotListResponse(items=records, total=len(records))

    def import_slot_candidates(
        self,
        recruiter_uid: str,
        slot_id: str,
        payload: CandidateCSVImportRequest,
    ) -> CandidateImportResponse:
        """Upload candidates into a slot from CSV."""

        slot = self._get_slot(recruiter_uid, slot_id)
        if slot is None:
            raise AssessmentNotFoundError("Assessment slot not found")
        existing_assignments = self._slot_candidate_assignments(recruiter_uid, slot_id)
        existing_emails = {item.email.lower() for item in existing_assignments}
        parsed = parse_candidate_csv(
            payload.csv_text,
            existing_emails=existing_emails,
        )
        created: list[SlotCandidateRecord] = []

        for row in parsed.valid_rows:
            candidate = self._get_or_create_candidate(
                recruiter_uid,
                row.name,
                row.email,
                row.external_id,
            )
            raw_token = token_urlsafe(32)
            token_hash = CandidateSessionService.hash_invite_token(
                raw_token,
                self._settings.invite_token_pepper,
            )
            assignment = CandidateAssessmentModel(
                assessment_id=slot.assessment_id,
                slot_id=slot.id,
                candidate_id=candidate.id,
                recruiter_uid=recruiter_uid,
                invite_token_hash=token_hash,
                email_status=InviteEmailStatus.PENDING.value,
                status=CandidateAssessmentStatus.NOT_STARTED.value,
            )
            self._repository.add(assignment)
            self._repository.flush()
            created.append(
                SlotCandidateRecord(
                    candidate_assessment_id=assignment.id,
                    candidate_id=candidate.id,
                    name=candidate.full_name,
                    email=candidate.email,
                    external_id=candidate.external_id,
                    invite_status=InviteEmailStatus(assignment.email_status),
                    assessment_status=CandidateAssessmentStatus(assignment.status),
                    hidden_checks_used=assignment.hidden_checks_used,
                    started_at=assignment.started_at,
                    submitted_at=assignment.submitted_at,
                    last_activity_at=assignment.last_activity_at,
                )
            )

        try:
            self._repository.commit()
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise AssessmentStoreUnavailableError(
                "Unable to import slot candidates"
            ) from exc

        return CandidateImportResponse(
            total_rows=parsed.total_rows,
            created_count=len(created),
            failed_count=len(parsed.errors),
            created=created,
            errors=parsed.errors,
        )

    def list_slot_candidates(
        self,
        recruiter_uid: str,
        slot_id: str,
    ) -> SlotCandidateListResponse:
        """Return recruiter-visible candidate assignments for a slot."""

        items = self._slot_candidate_assignments(recruiter_uid, slot_id)
        return SlotCandidateListResponse(items=items, total=len(items))

    def backfill_evaluations(
        self,
        recruiter_uid: str,
        assessment_id: str,
        payload: EvaluationBackfillRequest,
    ) -> EvaluationBackfillResponse:
        """Create evaluation jobs for prior submitted candidate assessments."""

        assessment = self._get_assessment(recruiter_uid, assessment_id)
        if assessment is None:
            raise AssessmentNotFoundError(assessment_id)

        try:
            assignments = self._repository.list_submitted_assignments_for_assessment(
                recruiter_uid=recruiter_uid,
                assessment_id=assessment_id,
                candidate_assessment_ids=payload.candidate_assessment_ids or None,
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError(
                "Unable to read submitted candidate assessments"
            ) from exc

        results = [
            self._backfill_candidate_evaluation(assignment, force=payload.force)
            for assignment in assignments
        ]
        if any(item.status == "evaluated" for item in results):
            self._sync_assessment_scores_from_leaderboard(
                recruiter_uid=recruiter_uid,
                assessment_id=assessment_id,
                fallback_assignments=assignments,
                include_all_submitted=False,
            )

        try:
            self._repository.commit()
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise AssessmentStoreUnavailableError(
                "Unable to persist evaluation backfill results"
            ) from exc

        with suppress(Exception):
            self._notification_service.flush_events()

        return EvaluationBackfillResponse(
            assessment_id=assessment_id,
            requested_count=len(assignments),
            evaluated_count=sum(1 for item in results if item.status == "evaluated"),
            skipped_count=sum(1 for item in results if item.status == "skipped"),
            failed_count=sum(1 for item in results if item.status == "failed"),
            results=results,
        )

    def get_evaluation_dashboard(
        self,
        recruiter_uid: str,
        assessment_id: str,
    ) -> AssessmentEvaluationDashboard:
        """Return evaluation analytics after verifying recruiter ownership."""

        assessment = self._require_owned_assessment(recruiter_uid, assessment_id)
        try:
            return self._evaluation_adapter.get_dashboard(assessment_id)
        except EvaluationResourceNotFoundError:
            return self._stored_evaluation_dashboard(recruiter_uid, assessment)

    def get_evaluation_report(
        self,
        recruiter_uid: str,
        assessment_id: str,
    ) -> AssessmentReportResponse:
        """Return assessment report data after verifying ownership."""

        assessment = self._require_owned_assessment(recruiter_uid, assessment_id)
        try:
            return self._evaluation_adapter.get_assessment_report(assessment_id)
        except EvaluationResourceNotFoundError:
            dashboard = self._stored_evaluation_dashboard(recruiter_uid, assessment)
            return AssessmentReportResponse(
                overview=dashboard.overview,
                leaderboard=dashboard.leaderboard,
                generated_at=dashboard.overview.generated_at,
                download_label=f"{assessment.title} evaluation report",
            )

    def get_candidate_evaluation_report(
        self,
        recruiter_uid: str,
        assessment_id: str,
        candidate_assessment_id: str,
    ) -> CandidateReportResponse:
        """Return one candidate scorecard after verifying assessment ownership."""

        assessment = self._require_owned_assessment(recruiter_uid, assessment_id)
        self._require_scorecard_eligible_candidate(
            recruiter_uid=recruiter_uid,
            assessment=assessment,
            candidate_assessment_id=candidate_assessment_id,
        )
        try:
            return self._evaluation_adapter.get_candidate_report(
                assessment_id,
                candidate_assessment_id,
            )
        except EvaluationResourceNotFoundError:
            candidate = self._stored_candidate_evaluation_summary_by_id(
                recruiter_uid=recruiter_uid,
                assessment=assessment,
                candidate_assessment_id=candidate_assessment_id,
            )
            if candidate is None:
                raise
            leaderboard = self._stored_evaluation_dashboard(
                recruiter_uid,
                assessment,
            ).leaderboard
            return CandidateReportResponse(
                assessment_id=assessment_id,
                candidate_assessment_id=candidate_assessment_id,
                candidate=candidate,
                benchmark=self._stored_candidate_benchmark(candidate, leaderboard),
                generated_at=datetime.now(UTC),
                download_label=f"{candidate.candidate_name} scorecard",
            )

    @staticmethod
    def _stored_candidate_benchmark(
        candidate: CandidateEvaluationSummary,
        leaderboard: list[CandidateEvaluationSummary],
    ) -> CandidateBenchmarkContext:
        completion_times = [
            item.time_taken_seconds
            for item in leaderboard
            if item.time_taken_seconds is not None
        ]
        total = len(leaderboard)
        return CandidateBenchmarkContext(
            candidate_rank=candidate.rank,
            total_candidates=total,
            average_score=(
                round(
                    sum(item.scores.final_score for item in leaderboard) / total,
                    2,
                )
                if total
                else None
            ),
            average_completion_time_seconds=(
                round(sum(completion_times) / len(completion_times))
                if completion_times
                else None
            ),
            percentile=(
                round(
                    sum(
                        1
                        for item in leaderboard
                        if item.scores.final_score <= candidate.scores.final_score
                    )
                    / total
                    * 100,
                    1,
                )
                if total
                else None
            ),
        )

    def retry_evaluation_job(
        self,
        recruiter_uid: str,
        assessment_id: str,
        job_id: str,
    ) -> RetryEvaluationResponse:
        """Retry a failed job only within a recruiter-owned assessment."""

        self._require_owned_assessment(recruiter_uid, assessment_id)
        response = self._evaluation_adapter.retry_job(job_id)
        if response.job.assessment_id != assessment_id:
            raise AssessmentNotFoundError("Evaluation job not found")
        return response

    def download_evaluation_report(
        self,
        recruiter_uid: str,
        assessment_id: str,
    ) -> EvaluationReportDownload:
        """Download an assessment PDF after verifying ownership."""

        self._require_owned_assessment(recruiter_uid, assessment_id)
        return self._evaluation_adapter.download_assessment_report(assessment_id)

    def download_candidate_evaluation_report(
        self,
        recruiter_uid: str,
        assessment_id: str,
        candidate_assessment_id: str,
    ) -> EvaluationReportDownload:
        """Download a candidate PDF after verifying assessment ownership."""

        assessment = self._require_owned_assessment(recruiter_uid, assessment_id)
        self._require_scorecard_eligible_candidate(
            recruiter_uid=recruiter_uid,
            assessment=assessment,
            candidate_assessment_id=candidate_assessment_id,
        )
        return self._evaluation_adapter.download_candidate_report(
            assessment_id,
            candidate_assessment_id,
        )

    def download_test_evaluation_report(
        self,
        recruiter_uid: str,
        assessment_id: str,
        slot_id: str,
    ) -> EvaluationReportDownload:
        """Download a report scoped to one recruiter-owned scheduled test."""

        assessment = self._require_owned_assessment(recruiter_uid, assessment_id)
        slot = self._get_slot(recruiter_uid, slot_id)
        if slot is None or slot.assessment_id != assessment_id:
            raise AssessmentNotFoundError("Test not found")
        candidates = self._slot_candidate_assignments(recruiter_uid, slot_id)
        scorecard_candidate_ids = [
            candidate.candidate_assessment_id
            for candidate in candidates
            if candidate.percentage is not None
            and candidate.percentage >= assessment.passing_score
            and candidate.rank is not None
        ]
        submitted_statuses = {
            CandidateAssessmentStatus.SUBMITTED,
            CandidateAssessmentStatus.AUTO_SUBMITTED,
        }
        return self._evaluation_adapter.download_test_report(
            assessment_id,
            slot_id,
            {
                "test_id": slot_id,
                "test_title": slot.title,
                "timezone_name": slot.timezone_name,
                "scheduled_start": (
                    slot.start_at.isoformat() if slot.start_at else None
                ),
                "scheduled_end": slot.end_at.isoformat() if slot.end_at else None,
                "candidate_count": len(candidates),
                "submitted_count": sum(
                    1
                    for candidate in candidates
                    if candidate.assessment_status in submitted_statuses
                ),
                "candidate_assessment_ids": scorecard_candidate_ids,
            },
        )

    def _sync_assessment_scores_from_leaderboard(
        self,
        *,
        recruiter_uid: str | None,
        assessment_id: str,
        fallback_assignments: list[CandidateAssessmentModel],
        include_all_submitted: bool = True,
    ) -> None:
        """Refresh submitted assignment scores/ranks from the leaderboard."""

        assignments = list(fallback_assignments)
        if recruiter_uid is not None and include_all_submitted:
            with suppress(SQLAlchemyError):
                assignments.extend(
                    self._repository.list_submitted_assignments_for_assessment(
                        recruiter_uid=recruiter_uid,
                        assessment_id=assessment_id,
                        candidate_assessment_ids=None,
                    )
                )
        self._sync_scores_from_leaderboard(assessment_id, assignments)

    def _sync_scores_from_leaderboard(
        self,
        assessment_id: str,
        assignments: list[CandidateAssessmentModel],
    ) -> None:
        """Update final scores/ranks from the evaluation service leaderboard."""

        assignments_by_id = {assignment.id: assignment for assignment in assignments}
        if not assignments_by_id:
            return
        try:
            leaderboard = self._evaluation_adapter.get_leaderboard(assessment_id)
        except EvaluationAdapterError:
            return
        for scorecard in leaderboard:
            assignment = assignments_by_id.get(scorecard.candidate_assessment_id)
            if assignment is None:
                continue
            assignment.total_score = scorecard.scores.final_score
            assignment.percentage = scorecard.scores.percentage
            assignment.rank = scorecard.rank

    @staticmethod
    def _empty_evaluation_dashboard(
        assessment: AssessmentTemplateModel,
        *,
        total_candidates: int = 0,
    ) -> AssessmentEvaluationDashboard:
        """Return a stable empty-state dashboard before evaluation jobs exist."""

        return AssessmentEvaluationDashboard(
            overview=AssessmentEvaluationOverview(
                assessment_id=assessment.id,
                title=assessment.title,
                total_candidates=total_candidates,
                completed_candidates=0,
                pending_jobs=0,
                failed_jobs=0,
                average_score=0,
                average_test_case_score=0,
                average_coding_score=0,
                average_ai_score=0,
                pass_rate=0,
                highest_score=0,
                report_status="pending",
                generated_at=datetime.now(UTC),
            ),
            leaderboard=[],
            jobs=[],
        )

    def _stored_evaluation_dashboard(
        self,
        recruiter_uid: str,
        assessment: AssessmentTemplateModel,
    ) -> AssessmentEvaluationDashboard:
        """Build result cards from core-stored score metadata as a fallback."""

        try:
            assignments = self._repository.list_submitted_assignments_for_assessment(
                recruiter_uid=recruiter_uid,
                assessment_id=assessment.id,
                candidate_assessment_ids=None,
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError(
                "Unable to read submitted candidate assessments"
            ) from exc

        summaries: list[CandidateEvaluationSummary] = []
        jobs_by_candidate: dict[str, EvaluationJobResponse] = {}
        for assignment in assignments:
            try:
                context = self._load_candidate_context_by_assignment(assignment)
            except (AssessmentStoreUnavailableError, CandidateInviteError):
                continue
            summary, job = self._stored_candidate_evaluation_from_context(context)
            if summary is None or job is None:
                continue
            summaries.append(summary)
            jobs_by_candidate[summary.candidate_assessment_id] = job

        if not summaries:
            return self._empty_evaluation_dashboard(
                assessment,
                total_candidates=len(assignments),
            )

        leaderboard = self._rank_evaluation_summaries(summaries)
        leaderboard_by_candidate = {
            item.candidate_assessment_id: item for item in leaderboard
        }
        jobs = [
            job.model_copy(
                update={
                    "result": leaderboard_by_candidate.get(
                        job.candidate_assessment_id,
                        job.result,
                    )
                }
            )
            for job in jobs_by_candidate.values()
        ]
        overview = self._stored_evaluation_overview(
            assessment=assessment,
            total_candidates=len(assignments),
            leaderboard=leaderboard,
            jobs=jobs,
        )
        return AssessmentEvaluationDashboard(
            overview=overview,
            leaderboard=leaderboard,
            jobs=sorted(jobs, key=lambda item: item.updated_at, reverse=True),
        )

    def _stored_candidate_evaluation_summary_by_id(
        self,
        *,
        recruiter_uid: str,
        assessment: AssessmentTemplateModel,
        candidate_assessment_id: str,
    ) -> CandidateEvaluationSummary | None:
        try:
            assignment = self._repository.get_candidate_assignment(
                recruiter_uid=recruiter_uid,
                candidate_assessment_id=candidate_assessment_id,
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError(
                "Unable to read candidate assessment"
            ) from exc
        if assignment is None or assignment.assessment_id != assessment.id:
            return None
        context = self._load_candidate_context_by_assignment(assignment)
        summary, _job = self._stored_candidate_evaluation_from_context(context)
        return summary

    def _stored_candidate_evaluation_from_context(
        self,
        context: CandidateAssessmentContext,
    ) -> tuple[CandidateEvaluationSummary | None, EvaluationJobResponse | None]:
        job_payload = self._stored_evaluation_job_payload(context)
        if job_payload is None:
            return None, None

        assignment = context.candidate_assessment
        result_payload = dict(job_payload.get("result") or {})
        submitted_at = assignment.submitted_at or datetime.now(UTC)
        updated_at = assignment.updated_at or submitted_at
        language = self._stored_submission_language(context)
        result_payload["question_breakdown"] = self._stored_question_breakdown(
            context,
            result_payload,
            language,
        )
        summary = CandidateEvaluationSummary.model_validate(
            {
                **result_payload,
                "assessment_id": context.assessment.id,
                "candidate_assessment_id": assignment.id,
                "candidate_id": context.candidate.id,
                "candidate_name": context.candidate.full_name,
                "candidate_email": context.candidate.email,
                "submission_id": assignment.id,
                "language": language,
                "status": job_payload.get("status") or "completed",
                "rank": assignment.rank or result_payload.get("rank"),
                "submitted_at": submitted_at,
                "evaluated_at": job_payload.get("updated_at") or updated_at,
                "time_taken_seconds": self._stored_time_taken_seconds(assignment),
            }
        )
        job = EvaluationJobResponse.model_validate(
            {
                "job_id": job_payload.get("job_id") or f"stored_{assignment.id}",
                "assessment_id": context.assessment.id,
                "candidate_assessment_id": assignment.id,
                "status": job_payload.get("status") or "completed",
                "attempt_count": job_payload.get("attempt_count") or 1,
                "created_at": job_payload.get("created_at") or submitted_at,
                "updated_at": job_payload.get("updated_at") or updated_at,
                "error_message": job_payload.get("error_message"),
                "result": summary,
            }
        )
        return summary, job

    @staticmethod
    def _stored_evaluation_job_payload(
        context: CandidateAssessmentContext,
    ) -> dict[str, Any] | None:
        for submission in context.submissions.values():
            result = dict(submission.final_hidden_result or {})
            evaluation_job = result.get("evaluation_job")
            if isinstance(evaluation_job, dict) and evaluation_job.get("result"):
                return evaluation_job
        return None

    @staticmethod
    def _stored_submission_language(context: CandidateAssessmentContext) -> str:
        for submission in context.submissions.values():
            if (submission.final_code or submission.draft_code).strip():
                return submission.source_language or "python"
        return "python"

    def _stored_question_breakdown(
        self,
        context: CandidateAssessmentContext,
        result_payload: dict[str, Any],
        language: str,
    ) -> list[dict[str, Any]]:
        breakdowns: list[dict[str, Any]] = []
        raw_breakdowns = result_payload.get("question_breakdown") or []
        if not isinstance(raw_breakdowns, list):
            return breakdowns
        for item in raw_breakdowns:
            if not isinstance(item, dict):
                continue
            question_id = str(item.get("question_id") or "")
            submission = context.submissions.get(question_id)
            enriched = dict(item)
            enriched["language"] = enriched.get("language") or (
                submission.source_language if submission is not None else language
            )
            enriched["submitted_code"] = enriched.get("submitted_code") or (
                (submission.final_code or submission.draft_code).strip()
                if submission is not None
                else ""
            )
            if not enriched.get("test_cases") and submission is not None:
                enriched["test_cases"] = self._stored_test_case_results(submission)
            breakdowns.append(enriched)
        return breakdowns

    @staticmethod
    def _stored_test_case_results(
        submission: SubmissionModel,
    ) -> list[dict[str, Any]]:
        final_hidden = dict(submission.final_hidden_result or {})
        raw_results = final_hidden.get("results") or []
        if not isinstance(raw_results, list):
            return []
        test_cases: list[dict[str, Any]] = []
        for index, result in enumerate(raw_results, start=1):
            if not isinstance(result, dict):
                continue
            case_index = result.get("index") or index
            status = str(result.get("status") or "")
            test_cases.append(
                {
                    "test_case_id": f"{submission.question_id}:{case_index}",
                    "passed": bool(result.get("passed")),
                    "verdict": AssessmentService._stored_verdict(status),
                    "execution_time_ms": AssessmentService._stored_execution_time_ms(
                        result.get("execution_time"),
                    ),
                    "memory_kb": result.get("memory_kb"),
                    "points": 1,
                    "mandatory": False,
                    "input": result.get("input") or "",
                    "expected_output": result.get("expected_output") or "",
                    "actual_output": result.get("actual_output") or "",
                    "message": (
                        result.get("message")
                        or result.get("stderr")
                        or result.get("compile_output")
                        or ""
                    ),
                }
            )
        return test_cases

    @staticmethod
    def _stored_verdict(status: str) -> str:
        normalized = status.strip().lower().replace(" ", "_")
        if "accepted" in normalized:
            return "accepted"
        if "compile" in normalized:
            return "compile_error"
        if "runtime" in normalized:
            return "runtime_error"
        if "time" in normalized or "timeout" in normalized:
            return "time_limit_exceeded"
        if "memory" in normalized:
            return "memory_limit_exceeded"
        return "wrong_answer"

    @staticmethod
    def _stored_execution_time_ms(value: Any) -> float | None:
        if value is None:
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed * 1000 if parsed < 100 else parsed

    @staticmethod
    def _stored_time_taken_seconds(
        assignment: CandidateAssessmentModel,
    ) -> int | None:
        if assignment.started_at is None or assignment.submitted_at is None:
            return None
        return max(
            0,
            int(
                (
                    assignment.submitted_at.astimezone(UTC)
                    - assignment.started_at.astimezone(UTC)
                ).total_seconds()
            ),
        )

    @staticmethod
    def _rank_evaluation_summaries(
        summaries: list[CandidateEvaluationSummary],
    ) -> list[CandidateEvaluationSummary]:
        ranked = sorted(
            summaries,
            key=lambda item: (
                -item.scores.final_score,
                -item.scores.test_case_score,
                -item.scores.coding_score,
                item.total_execution_time_ms,
                item.peak_memory_kb,
                item.time_taken_seconds or 0,
                item.submitted_at,
            ),
        )
        return [
            item.model_copy(update={"rank": index + 1})
            for index, item in enumerate(ranked)
        ]

    @staticmethod
    def _stored_evaluation_overview(
        *,
        assessment: AssessmentTemplateModel,
        total_candidates: int,
        leaderboard: list[CandidateEvaluationSummary],
        jobs: list[EvaluationJobResponse],
    ) -> AssessmentEvaluationOverview:
        scores = [item.scores for item in leaderboard]

        def average(values: list[float]) -> float:
            return sum(values) / len(values) if values else 0

        return AssessmentEvaluationOverview(
            assessment_id=assessment.id,
            title=assessment.title,
            total_candidates=total_candidates,
            completed_candidates=len(leaderboard),
            pending_jobs=max(total_candidates - len(leaderboard), 0),
            failed_jobs=sum(1 for job in jobs if job.status == "failed"),
            average_score=round(average([score.final_score for score in scores]), 2),
            average_test_case_score=round(
                average([score.test_case_score for score in scores]),
                2,
            ),
            average_coding_score=round(
                average([score.coding_score for score in scores]),
                2,
            ),
            average_ai_score=round(average([score.ai_score for score in scores]), 2),
            pass_rate=round(
                (
                    sum(1 for score in scores if score.final_score >= 40)
                    / len(scores)
                    * 100
                )
                if scores
                else 0,
                2,
            ),
            highest_score=round(
                max((score.final_score for score in scores), default=0),
                2,
            ),
            report_status="ready" if leaderboard else "pending",
            generated_at=datetime.now(UTC),
        )

    def count_dispatch_targets(
        self,
        recruiter_uid: str,
        slot_id: str,
        candidate_assessment_id: str | None = None,
        candidate_assessment_ids: list[str] | None = None,
    ) -> int:
        """Count invite-send targets before scheduling background delivery."""

        slot = self._get_slot(recruiter_uid, slot_id)
        if slot is None:
            raise AssessmentNotFoundError("Assessment slot not found")
        self._assert_slot_accepts_invites(slot)

        try:
            items = self._repository.list_invite_targets(
                recruiter_uid=recruiter_uid,
                slot_id=slot_id,
                candidate_assessment_id=candidate_assessment_id,
                candidate_assessment_ids=candidate_assessment_ids,
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError(
                "Unable to read invite targets"
            ) from exc
        if not items:
            raise CandidateInviteError(
                "No candidate invite targets found for this request"
            )
        return len(items)

    def get_candidate_assignment(
        self,
        recruiter_uid: str,
        candidate_assessment_id: str,
    ) -> CandidateAssessmentModel:
        """Return one recruiter-owned candidate assessment assignment."""

        try:
            assignment = self._repository.get_candidate_assignment(
                recruiter_uid=recruiter_uid,
                candidate_assessment_id=candidate_assessment_id,
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError(
                "Unable to read candidate assessment"
            ) from exc
        if assignment is None:
            raise AssessmentNotFoundError("Candidate assessment not found")
        return assignment

    def send_slot_invites(
        self,
        recruiter_uid: str,
        slot_id: str,
        candidate_assessment_id: str | None = None,
        candidate_assessment_ids: list[str] | None = None,
    ) -> InviteDispatchResponse:
        """Send invite emails for a slot, a single assignment, or selected rows."""

        slot = self._get_slot(recruiter_uid, slot_id)
        if slot is None:
            raise AssessmentNotFoundError("Assessment slot not found")
        self._assert_slot_accepts_invites(slot)
        assessment = self._get_assessment(recruiter_uid, slot.assessment_id)
        if assessment is None:
            raise AssessmentNotFoundError()

        try:
            assignments = self._repository.list_invite_targets(
                recruiter_uid=recruiter_uid,
                slot_id=slot_id,
                candidate_assessment_id=candidate_assessment_id,
                candidate_assessment_ids=candidate_assessment_ids,
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError(
                "Unable to load invite targets"
            ) from exc

        if not assignments:
            raise CandidateInviteError(
                "No candidate invite targets found for this request"
            )

        candidates = self._candidate_by_ids([item.candidate_id for item in assignments])
        sent = 0
        failed = 0
        now = datetime.now(UTC)

        for assignment in assignments:
            candidate = candidates.get(assignment.candidate_id)
            if candidate is None:
                failed += 1
                assignment.email_status = InviteEmailStatus.FAILED.value
                continue

            raw_token = token_urlsafe(32)
            assignment.invite_token_hash = CandidateSessionService.hash_invite_token(
                raw_token,
                self._settings.invite_token_pepper,
            )
            assignment.email_status = InviteEmailStatus.PENDING.value
            invite_base_url = self._settings.app_base_url.rstrip("/")
            invite_url = f"{invite_base_url}/candidate/invite/{raw_token}"
            instructions = slot.instructions_override.strip() or assessment.instructions

            try:
                self._invite_mail_service.send_assessment_invite(
                    to_email=candidate.email,
                    to_name=candidate.full_name,
                    assessment_title=assessment.title,
                    slot_title=slot.title,
                    invite_url=invite_url,
                    start_at=slot.start_at,
                    end_at=slot.end_at,
                    duration_minutes=(
                        slot.duration_minutes or assessment.duration_minutes
                    ),
                    instructions=instructions,
                )
                assignment.email_status = InviteEmailStatus.SENT.value
                assignment.invite_sent_at = now
                sent += 1
            except Exception:
                assignment.email_status = InviteEmailStatus.FAILED.value
                failed += 1

        try:
            self._repository.commit()
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise AssessmentStoreUnavailableError(
                "Unable to persist invite delivery"
            ) from exc

        return InviteDispatchResponse(
            slot_id=slot_id,
            requested=len(assignments),
            sent=sent,
            failed=failed,
            message="Invite delivery finished.",
        )

    def monitoring(self, recruiter_uid: str, slot_id: str) -> MonitoringResponse:
        """Return recruiter-visible monitoring for a slot."""

        # SSE reuses this service and SQLAlchemy session for the stream lifetime.
        # Expire the identity map so candidate updates committed by other requests
        # are visible on every snapshot instead of serving cached ORM objects.
        self._repository.expire_all()
        slot = self._get_slot(recruiter_uid, slot_id)
        if slot is None:
            raise AssessmentNotFoundError("Assessment slot not found")
        assessment = self._get_assessment(recruiter_uid, slot.assessment_id)
        if assessment is None:
            raise AssessmentNotFoundError()

        assignments = self._slot_assignment_models(recruiter_uid, slot_id)
        candidates = self._candidate_by_ids([item.candidate_id for item in assignments])
        submission_counts = self._submitted_question_counts(
            [item.id for item in assignments]
        )
        items = [
            MonitoringCandidateRecord(
                candidate_assessment_id=item.id,
                name=candidates[item.candidate_id].full_name
                if item.candidate_id in candidates
                else "Candidate",
                email=candidates[item.candidate_id].email
                if item.candidate_id in candidates
                else "",
                status=CandidateAssessmentStatus(item.status),
                started_at=item.started_at,
                submitted_at=item.submitted_at,
                last_activity_at=item.last_activity_at,
                questions_attempted=submission_counts.get(item.id, 0),
                hidden_checks_used=item.hidden_checks_used,
                submission_tag=item.submission_tag,
                submission_message=item.submission_message,
                current_question_order=item.current_question_order,
                time_remaining_seconds=time_remaining_seconds(item.deadline_at),
            )
            for item in assignments
        ]
        return MonitoringResponse(
            slot_id=slot.id,
            slot_title=slot.title,
            assessment_title=assessment.title,
            items=items,
            total=len(items),
        )

    def verify_invite(self, raw_token: str) -> CandidateInviteVerificationResponse:
        """Validate a raw invite token and return a candidate preview."""

        context = self._load_candidate_context_by_invite(raw_token)
        return CandidateInviteVerificationResponse(
            candidate_name=context.candidate.full_name,
            candidate_email=context.candidate.email,
            assessment_id=context.assessment.id,
            assessment_title=context.assessment.title,
            slot_id=context.slot.id,
            slot_title=context.slot.title,
            instructions=context.slot.instructions_override.strip()
            or context.assessment.instructions,
            duration_minutes=(
                getattr(context.slot, "duration_minutes", None)
                or context.assessment.duration_minutes
            ),
            start_at=context.slot.start_at,
            end_at=context.slot.end_at,
            allow_resume=context.assessment.allow_resume,
            status=CandidateAssessmentStatus(context.candidate_assessment.status),
            slot_status=effective_slot_status(context.slot),
            can_start=self._candidate_can_start(context),
        )

    def start_candidate_session(self, raw_token: str) -> CandidateStartResponse:
        """Create or resume a candidate portal session."""

        context = self._load_candidate_context_by_invite(raw_token)
        if not self._candidate_can_start(context):
            raise CandidateInviteError(
                "This invite is not currently valid for starting the assessment"
            )

        now = datetime.now(UTC)
        assignment = context.candidate_assessment
        assessment = context.assessment
        if (
            assignment.started_at is None
            or assignment.status == CandidateAssessmentStatus.NOT_STARTED.value
        ):
            assignment.started_at = now
            assignment.deadline_at = min(
                context.slot.end_at.astimezone(UTC),
                now
                + timedelta(
                    minutes=(
                        getattr(context.slot, "duration_minutes", None)
                        or assessment.duration_minutes
                    )
                ),
            )
        if assignment.deadline_at is None:
            assignment.deadline_at = min(
                context.slot.end_at.astimezone(UTC),
                now
                + timedelta(
                    minutes=(
                        getattr(context.slot, "duration_minutes", None)
                        or assessment.duration_minutes
                    )
                ),
            )
        session_deadline = assignment.deadline_at.astimezone(UTC)
        if (
            effective_slot_status(context.slot, now=now) == SlotStatus.PAUSED
            and context.slot.paused_at is not None
        ):
            session_deadline += now - context.slot.paused_at.astimezone(UTC)
        if session_deadline <= now:
            raise CandidateInviteError(
                "This assessment no longer has time remaining to start"
            )
        assignment.status = CandidateAssessmentStatus.IN_PROGRESS.value
        assignment.last_activity_at = now
        self._ensure_submission_rows(context)
        expires_at = self._candidate_session_service.expires_at_from_deadline(
            session_deadline
        )
        token = self._candidate_session_service.issue_session(
            candidate_assessment_id=assignment.id,
            assessment_id=assessment.id,
            slot_id=context.slot.id,
            candidate_id=context.candidate.id,
            expires_at=expires_at,
        )
        try:
            self._repository.commit()
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise AssessmentStoreUnavailableError(
                "Unable to start candidate session"
            ) from exc
        return CandidateStartResponse(
            session_token=token,
            expires_at=expires_at,
            candidate_assessment_id=assignment.id,
            status=CandidateAssessmentStatus(assignment.status),
        )

    def get_candidate_assessment(
        self,
        claims: CandidateSessionClaims,
    ) -> CandidateAssessmentPortalResponse:
        """Return the active candidate portal payload."""

        context = self._load_candidate_context_by_claims(claims)
        self._auto_submit_if_expired(context)
        context = self._load_candidate_context_by_claims(claims)
        if effective_slot_status(context.slot) in {
            SlotStatus.DRAFT,
            SlotStatus.SCHEDULED,
        }:
            raise AssessmentValidationError("This assessment is not active")

        instructions = (
            context.slot.instructions_override.strip()
            or context.assessment.instructions
        )
        ordered_questions = self._ordered_question_records(context)
        drafts = [
            CandidateQuestionDraftRecord(
                question_id=submission.question_id,
                source_language=submission.source_language,
                draft_code=submission.draft_code,
                final_code=submission.final_code,
                status=SubmissionStatus(submission.status),
                version=submission.version,
                sample_run_result=dict(submission.sample_run_result or {}),
                hidden_check_result=dict(submission.hidden_check_result or {}),
                submission_result=self._candidate_safe_submission_result(submission),
                last_saved_at=submission.last_saved_at,
                submitted_at=submission.submitted_at,
            )
            for submission in context.submissions.values()
        ]
        return CandidateAssessmentPortalResponse(
            candidate_name=context.candidate.full_name,
            candidate_email=context.candidate.email,
            candidate_assessment_id=context.candidate_assessment.id,
            assessment_id=context.assessment.id,
            assessment_title=context.assessment.title,
            slot_id=context.slot.id,
            slot_title=context.slot.title,
            instructions=instructions,
            duration_minutes=(
                getattr(context.slot, "duration_minutes", None)
                or context.assessment.duration_minutes
            ),
            allow_resume=context.assessment.allow_resume,
            proctoring_mode=context.assessment.proctoring_mode,
            hidden_feedback_mode=HiddenFeedbackMode(
                context.assessment.hidden_feedback_mode
            ),
            max_hidden_checks=0,
            hidden_check_cooldown_seconds=HIDDEN_CHECK_COOLDOWN_SECONDS,
            started_at=context.candidate_assessment.started_at,
            deadline_at=context.candidate_assessment.deadline_at,
            submitted_at=context.candidate_assessment.submitted_at,
            status=CandidateAssessmentStatus(context.candidate_assessment.status),
            slot_status=effective_slot_status(context.slot),
            current_question_order=context.candidate_assessment.current_question_order,
            time_remaining_seconds=self._candidate_time_remaining_seconds(context),
            tab_switch_count=context.candidate_assessment.tab_switch_count,
            copy_paste_count=context.candidate_assessment.copy_paste_count,
            fullscreen_exit_count=context.candidate_assessment.fullscreen_exit_count,
            question_time_seconds=dict(
                context.candidate_assessment.question_time_seconds or {}
            ),
            supported_languages=list(context.assessment.supported_languages or []),
            questions=ordered_questions,
            drafts=drafts,
        )

    def save_checkpoint(
        self,
        claims: CandidateSessionClaims,
        payload: CandidateCheckpointRequest,
    ) -> CandidateCheckpointResponse:
        """Save draft code for one question."""

        context = self._load_candidate_context_by_claims(claims)
        self._assert_candidate_can_edit(context)
        self._validate_question_language(context, payload.question_id, payload.language)
        submission = self._get_submission_for_question(context, payload.question_id)
        self._assert_draft_version(submission, payload.base_version)
        now = datetime.now(UTC)
        submission.draft_code = payload.source_code
        submission.source_language = payload.language.strip().lower()
        submission.last_saved_at = now
        submission.version += 1
        context.candidate_assessment.current_question_order = (
            payload.current_question_order
        )
        self._merge_candidate_activity_evidence(
            context.candidate_assessment,
            payload,
        )
        context.candidate_assessment.last_activity_at = now

        try:
            self._repository.commit()
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise AssessmentStoreUnavailableError(
                "Unable to save candidate checkpoint"
            ) from exc

        return CandidateCheckpointResponse(
            question_id=payload.question_id,
            saved_at=now,
            status=SubmissionStatus(submission.status),
            version=submission.version,
        )

    def run_sample(
        self,
        claims: CandidateSessionClaims,
        payload: CandidateCodeRunRequest,
    ) -> SampleRunResponse:
        """Run visible sample test cases for a question."""

        context = self._load_candidate_context_by_claims(claims)
        self._assert_candidate_can_edit(context)
        question = self._question_by_id(context, payload.question_id)
        self._validate_question_language(context, payload.question_id, payload.language)
        submission = self._get_submission_for_question(context, payload.question_id)
        self._assert_draft_version(submission, payload.base_version)
        sample_tests = complete_test_cases(question.sample_test_cases)
        results, passed_count, total_count = self._execute_candidate_test_batch(
            question=question,
            source_code=payload.source_code,
            language=payload.language.strip().lower(),
            test_cases=sample_tests,
            run_type="sample_run",
        )

        now = datetime.now(UTC)
        submission.draft_code = payload.source_code
        submission.source_language = payload.language.strip().lower()
        submission.sample_run_result = {
            "passed_count": passed_count,
            "total_count": total_count,
            "results": [item.model_dump(mode="json") for item in results],
        }
        submission.last_saved_at = now
        submission.version += 1
        context.candidate_assessment.last_activity_at = now

        try:
            self._repository.commit()
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise AssessmentStoreUnavailableError(
                "Unable to store sample run result"
            ) from exc

        return SampleRunResponse(
            question_id=payload.question_id,
            passed_count=passed_count,
            total_count=total_count,
            results=results,
            version=submission.version,
        )

    def run_hidden_check(
        self,
        claims: CandidateSessionClaims,
        payload: CandidateCodeRunRequest,
    ) -> HiddenCheckResponse:
        """Run a safe hidden-check summary for one question."""

        context = self._load_candidate_context_by_claims(claims)
        self._assert_candidate_can_edit(context)
        question = self._question_by_id(context, payload.question_id)
        self._validate_question_language(context, payload.question_id, payload.language)
        submission = self._get_submission_for_question(context, payload.question_id)
        self._assert_draft_version(submission, payload.base_version)

        assignment = context.candidate_assessment
        now = datetime.now(UTC)
        cooldown_remaining = hidden_check_cooldown_remaining(
            assignment.last_hidden_check_at,
            now,
        )
        if cooldown_remaining > 0:
            raise AssessmentValidationError(
                "Hidden check cooldown is active for another "
                f"{cooldown_remaining} seconds"
            )
        hidden_tests = complete_test_cases(question.hidden_test_cases)
        results, passed_count, total_count = self._execute_candidate_test_batch(
            question=question,
            source_code=payload.source_code,
            language=payload.language.strip().lower(),
            test_cases=hidden_tests,
            run_type="hidden_check",
        )
        assignment.hidden_checks_used += 1
        assignment.last_hidden_check_at = now
        assignment.last_activity_at = now
        submission.draft_code = payload.source_code
        submission.source_language = payload.language.strip().lower()
        submission.hidden_check_result = {
            "passed_count": passed_count,
            "total_count": total_count,
            "results": [
                {
                    "index": item.index,
                    "status": item.status,
                    "passed": item.passed,
                    "execution_time": item.execution_time,
                    "error_type": hidden_error_type(item),
                }
                for item in results
            ],
        }
        submission.last_saved_at = now
        submission.version += 1
        try:
            self._repository.commit()
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise AssessmentStoreUnavailableError(
                "Unable to store hidden-check result"
            ) from exc

        return HiddenCheckResponse(
            question_id=payload.question_id,
            passed_count=passed_count,
            total_count=total_count,
            remaining_attempts=None,
            cooldown_remaining_seconds=HIDDEN_CHECK_COOLDOWN_SECONDS,
            results=[
                HiddenExecutionCaseResult(
                    index=item.index,
                    status=item.status,
                    passed=item.passed,
                    execution_time=item.execution_time,
                    error_type=hidden_error_type(item),
                )
                for item in results
            ],
            version=submission.version,
        )

    def record_proctor_event(
        self,
        claims: CandidateSessionClaims,
        payload: CandidateProctorEventRequest,
    ) -> CandidateProctorEventResponse:
        """Persist one idempotent violation and increment server-owned counters."""

        context = self._load_candidate_context_by_claims(claims)
        self._assert_candidate_can_edit(context)
        assignment = context.candidate_assessment
        existing = self._repository.get_proctor_event(
            candidate_assessment_id=assignment.id,
            client_event_id=payload.client_event_id,
        )
        accepted = existing is None
        if accepted:
            event = CandidateProctorEventModel(
                candidate_assessment_id=assignment.id,
                client_event_id=payload.client_event_id,
                event_type=payload.event_type,
                occurred_at=payload.occurred_at.astimezone(UTC),
            )
            self._repository.add(event)
            if payload.event_type in {"tab_hidden", "window_blur"}:
                assignment.tab_switch_count += 1
            elif payload.event_type == "clipboard":
                assignment.copy_paste_count += 1
            elif payload.event_type == "fullscreen_exit":
                assignment.fullscreen_exit_count += 1
            assignment.last_activity_at = datetime.now(UTC)
            try:
                self._repository.commit()
            except SQLAlchemyError as exc:
                self._repository.rollback()
                raise AssessmentStoreUnavailableError(
                    "Unable to store proctoring event"
                ) from exc

        return CandidateProctorEventResponse(
            accepted=accepted,
            tab_switch_count=assignment.tab_switch_count,
            copy_paste_count=assignment.copy_paste_count,
            fullscreen_exit_count=assignment.fullscreen_exit_count,
        )

    def submit_assessment(
        self,
        claims: CandidateSessionClaims,
        payload: CandidateSubmitRequest,
        *,
        auto_submit: bool = False,
    ) -> CandidateSubmitResponse:
        """Finalize all answers for evaluation."""

        context = self._load_candidate_context_by_claims(claims)
        if context.candidate_assessment.status in {
            CandidateAssessmentStatus.SUBMITTED.value,
            CandidateAssessmentStatus.AUTO_SUBMITTED.value,
        }:
            submitted_at = context.candidate_assessment.submitted_at
            if submitted_at is None:
                submitted_at = datetime.now(UTC)
            return CandidateSubmitResponse(
                candidate_assessment_id=context.candidate_assessment.id,
                status=CandidateAssessmentStatus(context.candidate_assessment.status),
                submitted_at=submitted_at,
                pending_evaluation=(
                    getattr(context.candidate_assessment, "percentage", None) is None
                ),
                submission_tag=context.candidate_assessment.submission_tag,
                submission_message=context.candidate_assessment.submission_message,
            )

        if not auto_submit:
            slot_status = effective_slot_status(context.slot)
            deadline = context.candidate_assessment.deadline_at
            if slot_status == SlotStatus.CLOSED or (
                deadline is not None and datetime.now(UTC) > deadline.astimezone(UTC)
            ):
                self._auto_submit_if_expired(context)
                return self.submit_assessment(claims, payload, auto_submit=True)
            self._assert_candidate_can_edit(context)

        answer_by_question = {item.question_id: item for item in payload.answers}
        summaries: list[SubmissionExecutionSummary] = []
        now = datetime.now(UTC)

        assignment = context.candidate_assessment
        self._merge_candidate_activity_evidence(assignment, payload)
        assignment.submission_tag = payload.submission_tag.strip()
        assignment.submission_message = payload.submission_message.strip()

        delivered_mappings = self._candidate_question_mappings(context)
        question_by_id = {question.id: question for question in context.questions}
        delivered_questions = [
            question
            for mapping in delivered_mappings
            if (question := question_by_id.get(mapping.question_id)) is not None
        ]

        for question in delivered_questions:
            submission = self._get_submission_for_question(context, question.id)
            answer = answer_by_question.get(question.id)
            if answer is not None:
                self._validate_question_language(context, question.id, answer.language)
                submission.draft_code = answer.source_code
                submission.source_language = answer.language.strip().lower()
                submission.version += 1
            source_code = submission.draft_code.strip()
            if not source_code:
                source_code = submission.final_code.strip()
            hidden_tests = complete_test_cases(question.hidden_test_cases)
            if not source_code:
                submission.final_code = ""
                submission.status = SubmissionStatus.SKIPPED_EVALUATION.value
                submission.final_hidden_result = {
                    "skipped": True,
                    "reason": "empty_submission",
                    "passed_count": 0,
                    "total_count": 0,
                    "results": [],
                }
                submission.submitted_at = now
                continue
            if not hidden_tests:
                results: list[ExecutionCaseResult] = []
                passed_count = 0
                total_count = 0
            else:
                try:
                    (
                        results,
                        passed_count,
                        total_count,
                    ) = self._execute_candidate_test_batch(
                        question=question,
                        source_code=source_code,
                        language=submission.source_language,
                        test_cases=hidden_tests,
                        run_type="final_hidden",
                    )
                except ExecutionAdapterError:
                    results = execution_failed_results(hidden_tests)
                    passed_count = 0
                    total_count = len(hidden_tests)
            submission.final_code = source_code
            submission.status = SubmissionStatus.PENDING_EVALUATION.value
            submission.final_hidden_result = {
                "passed_count": passed_count,
                "total_count": total_count,
                "results": [item.model_dump(mode="json") for item in results],
            }
            submission.submitted_at = now
            summaries.append(
                SubmissionExecutionSummary(
                    question_id=question.id,
                    passed_count=passed_count,
                    total_count=total_count,
                    results=results,
                )
            )

        earned_score, percentage = self._initial_screen_score(
            delivered_mappings,
            summaries,
        )
        passed_initial_screen = percentage >= float(
            getattr(context.assessment, "passing_score", 0),
        )
        evaluation_job = None
        has_submitted_source = any(
            self._get_submission_for_question(context, question.id).final_code.strip()
            for question in delivered_questions
        )
        if passed_initial_screen and summaries and has_submitted_source:
            try:
                evaluation_job = self._evaluation_adapter.create_job(
                    self._evaluation_payload_from_context(
                        context=context,
                        mappings=delivered_mappings,
                        questions=delivered_questions,
                        submissions=[
                            self._get_submission_for_question(context, question.id)
                            for question in delivered_questions
                        ],
                        summaries=summaries,
                        submitted_at=now,
                    )
                )
            except EvaluationAdapterError:
                evaluation_job = None

        if evaluation_job is not None and evaluation_job.result is not None:
            context.candidate_assessment.total_score = (
                evaluation_job.result.scores.final_score
            )
            context.candidate_assessment.percentage = (
                evaluation_job.result.scores.percentage
            )
            context.candidate_assessment.rank = evaluation_job.result.rank
            self._attach_evaluation_metadata(
                context=context,
                question_ids=[question.id for question in delivered_questions],
                evaluation_job=evaluation_job,
            )

        submission_status = (
            SubmissionStatus.PENDING_EVALUATION.value
            if evaluation_job is not None or passed_initial_screen
            else SubmissionStatus.SKIPPED_EVALUATION.value
        )
        for question in delivered_questions:
            submission = self._get_submission_for_question(context, question.id)
            submission.status = (
                submission_status
                if (submission.final_code or submission.draft_code).strip()
                else SubmissionStatus.SKIPPED_EVALUATION.value
            )

        should_auto_submit = auto_submit or payload.auto_submit
        context.candidate_assessment.status = (
            CandidateAssessmentStatus.AUTO_SUBMITTED.value
            if should_auto_submit
            else CandidateAssessmentStatus.SUBMITTED.value
        )
        context.candidate_assessment.submitted_at = now
        context.candidate_assessment.last_activity_at = now
        if evaluation_job is None or evaluation_job.result is None:
            context.candidate_assessment.total_score = earned_score
            context.candidate_assessment.percentage = percentage
        else:
            self._sync_assessment_scores_from_leaderboard(
                recruiter_uid=getattr(context.assessment, "recruiter_uid", None),
                assessment_id=context.assessment.id,
                fallback_assignments=[context.candidate_assessment],
            )

        evaluation_completed = (
            evaluation_job is not None and evaluation_job.result is not None
        )
        self._notify_candidate_events(
            context=context,
            notify_submission=True,
            notify_evaluation=evaluation_completed,
        )

        try:
            self._repository.commit()
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise AssessmentStoreUnavailableError(
                "Unable to submit assessment"
            ) from exc

        with suppress(Exception):
            self._notification_service.flush_events()

        return CandidateSubmitResponse(
            candidate_assessment_id=context.candidate_assessment.id,
            status=CandidateAssessmentStatus(context.candidate_assessment.status),
            submitted_at=now,
            pending_evaluation=evaluation_job is not None or passed_initial_screen,
            submission_tag=context.candidate_assessment.submission_tag,
            submission_message=context.candidate_assessment.submission_message,
        )

    @staticmethod
    def _merge_candidate_activity_evidence(
        assignment: CandidateAssessmentModel,
        payload: CandidateCheckpointRequest | CandidateSubmitRequest,
    ) -> None:
        """Merge timing evidence without trusting client-supplied violation totals."""

        # Violation counters are incremented only by record_proctor_event. Legacy
        # aggregate fields remain in the payload for rollout compatibility but are
        # intentionally ignored so a browser cannot reset or replace server totals.
        merged_times = dict(assignment.question_time_seconds or {})
        for question_id, seconds in payload.question_time_seconds.items():
            merged_times[question_id] = max(
                merged_times.get(question_id, 0),
                seconds,
            )
        assignment.question_time_seconds = merged_times

    def _backfill_candidate_evaluation(
        self,
        assignment: CandidateAssessmentModel,
        *,
        force: bool,
    ) -> EvaluationBackfillCandidateResult:
        try:
            context = self._load_candidate_context_by_assignment(assignment)
        except (AssessmentStoreUnavailableError, CandidateInviteError) as exc:
            return EvaluationBackfillCandidateResult(
                candidate_assessment_id=assignment.id,
                status="failed",
                message=str(exc),
            )

        delivered_mappings = self._candidate_question_mappings(context)
        question_by_id = {question.id: question for question in context.questions}
        delivered_questions = [
            question
            for mapping in delivered_mappings
            if (question := question_by_id.get(mapping.question_id)) is not None
        ]
        delivered_submissions = [
            self._get_submission_for_question(context, question.id)
            for question in delivered_questions
        ]

        if not force and self._has_evaluation_job_metadata(delivered_submissions):
            return EvaluationBackfillCandidateResult(
                candidate_assessment_id=assignment.id,
                status="skipped",
                message="Evaluation job already exists for this submission.",
            )

        if not any(
            (submission.final_code or submission.draft_code).strip()
            for submission in delivered_submissions
        ):
            return EvaluationBackfillCandidateResult(
                candidate_assessment_id=assignment.id,
                status="skipped",
                message="No submitted source code was found.",
            )

        submitted_at = assignment.submitted_at or datetime.now(UTC)
        summaries = self._final_hidden_summaries_for_backfill(
            questions=delivered_questions,
            submissions=delivered_submissions,
            submitted_at=submitted_at,
        )
        if not summaries:
            return EvaluationBackfillCandidateResult(
                candidate_assessment_id=assignment.id,
                status="skipped",
                message="No final hidden execution evidence could be produced.",
            )

        earned_score, percentage = self._initial_screen_score(
            delivered_mappings,
            summaries,
        )
        passing_score = float(getattr(context.assessment, "passing_score", 0))
        if percentage < passing_score:
            assignment.total_score = earned_score
            assignment.percentage = percentage
            assignment.rank = None
            for submission in delivered_submissions:
                submission.status = SubmissionStatus.SKIPPED_EVALUATION.value
            return EvaluationBackfillCandidateResult(
                candidate_assessment_id=assignment.id,
                status="skipped",
                message=(
                    f"Initial score {percentage:.2f}% did not meet the "
                    f"{passing_score:.2f}% pass mark; no scorecard was created."
                ),
            )

        try:
            evaluation_payload = self._evaluation_payload_from_context(
                context=context,
                mappings=delivered_mappings,
                questions=delivered_questions,
                submissions=delivered_submissions,
                summaries=summaries,
                submitted_at=submitted_at,
            )
            if force:
                evaluation_payload["force"] = True
            evaluation_job = self._evaluation_adapter.create_job(evaluation_payload)
        except EvaluationAdapterError as exc:
            return EvaluationBackfillCandidateResult(
                candidate_assessment_id=assignment.id,
                status="failed",
                message=str(exc),
            )

        if evaluation_job.result is None:
            return EvaluationBackfillCandidateResult(
                candidate_assessment_id=assignment.id,
                status="failed",
                evaluation_job_id=evaluation_job.job_id,
                message=evaluation_job.error_message
                or "Evaluation service did not return a scorecard.",
            )

        assignment.total_score = evaluation_job.result.scores.final_score
        assignment.percentage = evaluation_job.result.scores.percentage
        assignment.rank = evaluation_job.result.rank
        self._attach_evaluation_metadata(
            context=context,
            question_ids=[question.id for question in delivered_questions],
            evaluation_job=evaluation_job,
        )
        for submission in delivered_submissions:
            submission.status = (
                SubmissionStatus.PENDING_EVALUATION.value
                if (submission.final_code or submission.draft_code).strip()
                else SubmissionStatus.SKIPPED_EVALUATION.value
            )

        self._notify_candidate_events(
            context=context,
            notify_submission=False,
            notify_evaluation=True,
        )

        return EvaluationBackfillCandidateResult(
            candidate_assessment_id=assignment.id,
            status="evaluated",
            message="Evaluation job created and scorecard stored.",
            evaluation_job_id=evaluation_job.job_id,
            final_score=evaluation_job.result.scores.final_score,
            rank=evaluation_job.result.rank,
        )

    @staticmethod
    def _initial_screen_score(
        mappings: list[Any],
        summaries: list[SubmissionExecutionSummary],
    ) -> tuple[float, float]:
        """Return the weighted hidden-test score used to gate evaluation."""

        total_possible_score = (
            sum(float(getattr(mapping, "marks", 1)) for mapping in mappings) or 1
        )
        summary_by_question = {summary.question_id: summary for summary in summaries}
        earned_score = 0.0
        for mapping in mappings:
            summary = summary_by_question.get(mapping.question_id)
            if summary is None:
                continue
            pass_ratio = (
                summary.passed_count / summary.total_count
                if summary.total_count > 0
                else 0.0
            )
            earned_score += float(getattr(mapping, "marks", 1)) * pass_ratio
        percentage = (earned_score / total_possible_score) * 100
        return earned_score, percentage

    def _require_scorecard_eligible_candidate(
        self,
        *,
        recruiter_uid: str,
        assessment: AssessmentTemplateModel,
        candidate_assessment_id: str,
    ) -> CandidateAssessmentModel:
        """Reject scorecard access when the candidate did not meet the pass mark."""

        try:
            assignment = self._repository.get_candidate_assignment(
                recruiter_uid=recruiter_uid,
                candidate_assessment_id=candidate_assessment_id,
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError(
                "Unable to read candidate assessment"
            ) from exc
        if assignment is None or assignment.assessment_id != assessment.id:
            raise AssessmentNotFoundError("Candidate assessment not found")
        if (
            assignment.percentage is not None
            and assignment.percentage < assessment.passing_score
        ):
            raise EvaluationResourceNotFoundError(
                "Scorecard is not available because the candidate did not meet "
                "the assessment pass mark."
            )
        return assignment

    def _notify_candidate_events(
        self,
        *,
        context: CandidateAssessmentContext,
        notify_submission: bool,
        notify_evaluation: bool,
    ) -> None:
        """Emit recruiter dashboard notifications without breaking the flow."""

        recruiter_uid = getattr(context.assessment, "recruiter_uid", None)
        if not recruiter_uid:
            return
        assessment_id = context.assessment.id
        assessment_title = getattr(context.assessment, "title", "") or ""
        slot_id = context.slot.id
        slot_title = getattr(context.slot, "title", "") or ""
        candidate_name = getattr(context.candidate, "full_name", "") or "A candidate"

        if notify_submission:
            try:
                self._notification_service.record_submission(
                    recruiter_uid=recruiter_uid,
                    assessment_id=assessment_id,
                    assessment_title=assessment_title,
                    slot_id=slot_id,
                    slot_title=slot_title,
                    candidate_name=candidate_name,
                )
            except Exception:
                logger.warning(
                    "Failed to record submission notification for recruiter %s",
                    recruiter_uid,
                    exc_info=True,
                )
        if notify_evaluation:
            try:
                self._notification_service.record_evaluation(
                    recruiter_uid=recruiter_uid,
                    assessment_id=assessment_id,
                    assessment_title=assessment_title,
                    slot_id=slot_id,
                    slot_title=slot_title,
                    candidate_name=candidate_name,
                )
            except Exception:
                logger.warning(
                    "Failed to record evaluation notification for recruiter %s",
                    recruiter_uid,
                    exc_info=True,
                )

    def _final_hidden_summaries_for_backfill(
        self,
        *,
        questions: list[QuestionBankQuestionModel],
        submissions: list[SubmissionModel],
        submitted_at: datetime,
    ) -> list[SubmissionExecutionSummary]:
        stored_summaries = self._stored_final_hidden_summaries(submissions)
        stored_question_ids = {summary.question_id for summary in stored_summaries}
        submissions_by_question = {
            submission.question_id: submission for submission in submissions
        }
        generated_summaries: list[SubmissionExecutionSummary] = []

        for question in questions:
            if question.id in stored_question_ids:
                continue
            submission = submissions_by_question.get(question.id)
            if submission is None:
                continue
            if not (submission.final_code or submission.draft_code).strip():
                continue
            generated_summaries.append(
                self._execute_final_hidden_for_backfill(
                    question=question,
                    submission=submission,
                    submitted_at=submitted_at,
                )
            )

        return stored_summaries + generated_summaries

    def _execute_final_hidden_for_backfill(
        self,
        *,
        question: QuestionBankQuestionModel,
        submission: SubmissionModel,
        submitted_at: datetime,
    ) -> SubmissionExecutionSummary:
        source_code = (submission.final_code or submission.draft_code).strip()
        if not source_code:
            raise ValueError("Empty submissions must not be evaluated.")
        hidden_tests = complete_test_cases(question.hidden_test_cases)
        if not can_execute_final_submission(
            source_code,
            submission.source_language,
            hidden_tests,
        ):
            results = not_attempted_results(hidden_tests)
            passed_count = 0
            total_count = len(hidden_tests)
        else:
            try:
                (
                    results,
                    passed_count,
                    total_count,
                ) = self._execute_candidate_test_batch(
                    question=question,
                    source_code=source_code,
                    language=submission.source_language,
                    test_cases=hidden_tests,
                    run_type="final_hidden",
                )
            except ExecutionAdapterError:
                results = execution_failed_results(hidden_tests)
                passed_count = 0
                total_count = len(hidden_tests)

        submission.final_code = source_code
        submission.final_hidden_result = {
            "passed_count": passed_count,
            "total_count": total_count,
            "results": [item.model_dump(mode="json") for item in results],
        }
        submission.submitted_at = submission.submitted_at or submitted_at
        return SubmissionExecutionSummary(
            question_id=question.id,
            passed_count=passed_count,
            total_count=total_count,
            results=results,
        )

    @staticmethod
    def _score_results_for_question(
        question: QuestionBankQuestionModel,
        results: list[ExecutionCaseResult],
    ) -> tuple[list[ExecutionCaseResult], int, int]:
        scored_results = [
            apply_answer_validation(
                result,
                mode=getattr(question, "answer_validation_mode", "exact") or "exact",
                checker_source=getattr(question, "output_checker", "") or "",
            )
            for result in results
        ]
        return (
            scored_results,
            sum(1 for result in scored_results if result.passed),
            len(scored_results),
        )

    def _execute_candidate_test_batch(
        self,
        *,
        question: QuestionBankQuestionModel,
        source_code: str,
        language: str,
        test_cases: list[TestCase],
        run_type: str,
    ) -> tuple[list[ExecutionCaseResult], int, int]:
        """Run one candidate source against all required cases in one batch."""

        results, _, _ = self._execution_adapter.execute_batch(
            source_code=source_code,
            language=language,
            test_cases=test_cases,
            run_type=run_type,
            time_limit_seconds=(
                getattr(question, "execution_time_limit_seconds", 2) or 2
            ),
            memory_limit_kb=((getattr(question, "memory_limit_mb", 256) or 256) * 1024),
        )
        return self._score_results_for_question(question, results)

    @staticmethod
    def _has_evaluation_job_metadata(submissions: list[SubmissionModel]) -> bool:
        for submission in submissions:
            if not (submission.final_code or submission.draft_code).strip():
                continue
            final_hidden_result = submission.final_hidden_result or {}
            if isinstance(final_hidden_result, dict) and final_hidden_result.get(
                "evaluation_job"
            ):
                return True
        return False

    @staticmethod
    def _stored_final_hidden_summaries(
        submissions: list[SubmissionModel],
    ) -> list[SubmissionExecutionSummary]:
        summaries: list[SubmissionExecutionSummary] = []
        for submission in submissions:
            final_hidden_result = submission.final_hidden_result or {}
            if not isinstance(final_hidden_result, dict):
                continue
            raw_results = final_hidden_result.get("results")
            if not isinstance(raw_results, list) or not raw_results:
                continue
            results = [
                ExecutionCaseResult.model_validate(item)
                for item in raw_results
                if isinstance(item, dict)
            ]
            if not results:
                continue
            passed_value = final_hidden_result.get("passed_count")
            total_value = final_hidden_result.get("total_count")
            summaries.append(
                SubmissionExecutionSummary(
                    question_id=submission.question_id,
                    passed_count=(passed_value if type(passed_value) is int else 0),
                    total_count=(
                        total_value if type(total_value) is int else len(results)
                    ),
                    results=results,
                )
            )
        return summaries

    def _evaluation_payload_from_context(
        self,
        *,
        context: CandidateAssessmentContext,
        mappings: list[AssessmentQuestionModel | DeliveredQuestionMapping],
        questions: list[QuestionBankQuestionModel],
        submissions: list[SubmissionModel],
        summaries: list[SubmissionExecutionSummary],
        submitted_at: datetime,
    ) -> dict[str, Any]:
        return build_evaluation_payload(
            assessment=context.assessment,
            candidate=context.candidate,
            candidate_assessment=context.candidate_assessment,
            mappings=mappings,
            questions=questions,
            submissions=submissions,
            summaries=summaries,
            submitted_at=submitted_at,
        )

    def _attach_evaluation_metadata(
        self,
        *,
        context: CandidateAssessmentContext,
        question_ids: list[str],
        evaluation_job: Any,
    ) -> None:
        for question_id in question_ids:
            submission = self._get_submission_for_question(context, question_id)
            current = dict(submission.final_hidden_result or {})
            current["evaluation_job"] = evaluation_job.model_dump(mode="json")
            submission.final_hidden_result = current

    def _get_assessment(
        self,
        recruiter_uid: str,
        assessment_id: str,
    ) -> AssessmentTemplateModel | None:
        try:
            return self._repository.get_assessment(
                recruiter_uid=recruiter_uid,
                assessment_id=assessment_id,
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError("Unable to read assessment") from exc

    def _require_owned_assessment(
        self,
        recruiter_uid: str,
        assessment_id: str,
    ) -> AssessmentTemplateModel:
        assessment = self._get_assessment(recruiter_uid, assessment_id)
        if assessment is None:
            raise AssessmentNotFoundError(assessment_id)
        return assessment

    def _get_slot(self, recruiter_uid: str, slot_id: str) -> AssessmentSlotModel | None:
        try:
            return self._repository.get_slot(
                recruiter_uid=recruiter_uid,
                slot_id=slot_id,
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError(
                "Unable to read assessment slot"
            ) from exc

    def _slots_for_assessment(
        self,
        recruiter_uid: str,
        assessment_id: str,
    ) -> list[AssessmentSlotModel]:
        try:
            return self._repository.list_slots_for_assessment(
                recruiter_uid=recruiter_uid,
                assessment_id=assessment_id,
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError(
                "Unable to read assessment slots"
            ) from exc

    def _assessment_record_from_model(
        self,
        model: AssessmentTemplateModel,
        recruiter_uid: str,
    ) -> AssessmentRecord:
        mappings = self._assessment_mappings(model.id)
        questions = self._question_bank_records(
            recruiter_uid,
            [item.question_id for item in mappings],
        )
        question_by_id = {item.id: item for item in questions}
        records = [
            AssessmentQuestionRecord(
                question_id=mapping.question_id,
                title=question_by_id[mapping.question_id].title,
                difficulty=DifficultyLevel(
                    question_by_id[mapping.question_id].difficulty
                ),
                tags=list(question_by_id[mapping.question_id].tags or []),
                question_order=mapping.question_order,
                marks=mapping.marks,
                is_mandatory=mapping.is_mandatory,
                supported_languages=list(
                    question_by_id[mapping.question_id].supported_languages or []
                ),
            )
            for mapping in mappings
            if mapping.question_id in question_by_id
        ]
        slots = self._slots_for_assessment(recruiter_uid, model.id)
        candidate_assessments = self._candidate_assessments_for_slot_ids(
            [slot.id for slot in slots],
        )
        slot_records = [
            slot_summary_from_model(
                slot,
                candidate_count=len(candidate_assessments.get(slot.id, [])),
                submitted_count=submitted_assignment_count(
                    candidate_assessments.get(slot.id, []),
                ),
            )
            for slot in slots
        ]
        visible_slot_records = [
            slot
            for slot in slot_records
            if slot.effective_status
            in {
                SlotStatus.SCHEDULED,
                SlotStatus.ACTIVE,
                SlotStatus.PAUSED,
            }
        ]
        live_test_count = sum(
            1
            for slot in slot_records
            if slot.effective_status in {SlotStatus.ACTIVE, SlotStatus.PAUSED}
        )
        scheduled_test_count = sum(
            1 for slot in slot_records if slot.effective_status == SlotStatus.SCHEDULED
        )
        return AssessmentRecord(
            id=model.id,
            recruiter_uid=model.recruiter_uid,
            title=model.title,
            description=model.description,
            instructions=model.instructions,
            duration_minutes=model.duration_minutes,
            passing_score=model.passing_score,
            test_case_score_weight=model.test_case_score_weight,
            coding_score_weight=model.coding_score_weight,
            ai_score_weight=model.ai_score_weight,
            allow_resume=model.allow_resume,
            shuffle_questions=model.shuffle_questions,
            question_count_per_candidate=model.question_count_per_candidate,
            difficulty_blueprint=[
                DifficultyLevel(item) for item in (model.difficulty_blueprint or [])
            ],
            show_score_to_candidate=model.show_score_to_candidate,
            proctoring_mode=model.proctoring_mode,
            hidden_feedback_mode=HiddenFeedbackMode(model.hidden_feedback_mode),
            max_hidden_checks=0,
            hidden_check_cooldown_seconds=HIDDEN_CHECK_COOLDOWN_SECONDS,
            supported_languages=list(model.supported_languages or []),
            status=assessment_status_from_slots(model, slot_records),
            questions=records,
            question_count=len(records),
            slots=visible_slot_records,
            test_count=len(slot_records),
            scheduled_test_count=scheduled_test_count,
            live_test_count=live_test_count,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _assessment_mappings(self, assessment_id: str) -> list[AssessmentQuestionModel]:
        try:
            return self._repository.list_assessment_questions(assessment_id)
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError(
                "Unable to read assessment questions"
            ) from exc

    def _validate_assessment_questions(
        self,
        recruiter_uid: str,
        assessment: AssessmentTemplateModel,
        questions: list[Any],
    ) -> list[dict[str, Any]]:
        if not questions:
            raise AssessmentValidationError(
                "An assessment must contain at least one question"
            )

        normalized: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        question_ids = []
        for item in questions:
            question_id = item.question_id.strip()
            if question_id in seen_ids:
                raise AssessmentValidationError("Assessment questions must be unique")
            seen_ids.add(question_id)
            question_ids.append(question_id)
            normalized.append(
                {
                    "question_id": question_id,
                    "question_order": item.question_order,
                    "marks": item.marks,
                    "is_mandatory": item.is_mandatory,
                }
            )

        records = self._question_bank_records(recruiter_uid, question_ids)
        if len(records) != len(question_ids):
            raise AssessmentValidationError(
                "One or more questions do not exist in the recruiter question bank"
            )
        record_by_id = {item.id: item for item in records}
        invalid = [
            item.title
            for item in records
            if item.status != QuestionStatus.VALIDATED.value
        ]
        if invalid:
            raise AssessmentValidationError(
                "Only validated questions can be added to an assessment"
            )
        self._assert_assessment_language_coverage(
            list(assessment.supported_languages or []),
            records,
        )
        question_count = int(assessment.question_count_per_candidate or 0)
        blueprint = list(assessment.difficulty_blueprint or [])
        if question_count <= 0:
            question_count = len(blueprint) or len(normalized)
        if len(blueprint) != question_count:
            raise AssessmentValidationError(
                "Difficulty template must contain one entry for every "
                "delivered question"
            )
        if assessment.shuffle_questions:
            if len(normalized) < question_count:
                raise AssessmentValidationError(
                    "Randomized assessments require a pool at least as large "
                    "as the question count"
                )
            available = {
                difficulty: sum(
                    1
                    for question_id in question_ids
                    if record_by_id[question_id].difficulty == difficulty
                )
                for difficulty in {item.value for item in DifficultyLevel}
            }
            required = {
                difficulty: blueprint.count(difficulty)
                for difficulty in {item.value for item in DifficultyLevel}
            }
            if any(available[item] < required[item] for item in required):
                raise AssessmentValidationError(
                    "Randomized question pool cannot satisfy the difficulty template"
                )
            unsupported = sorted(
                {
                    record_by_id[question_id].difficulty
                    for question_id in question_ids
                    if record_by_id[question_id].difficulty not in blueprint
                }
            )
            if unsupported:
                raise AssessmentValidationError(
                    "Question pool contains difficulties outside the template: "
                    + ", ".join(unsupported)
                )
        else:
            if len(normalized) != question_count:
                raise AssessmentValidationError(
                    f"Same-set assessments require exactly {question_count} questions"
                )
            ordered = sorted(normalized, key=lambda item: item["question_order"])
            if any(
                record_by_id[item["question_id"]].difficulty != blueprint[index]
                for index, item in enumerate(ordered)
            ):
                raise AssessmentValidationError(
                    "Selected question order must match the difficulty template"
                )
        template_marks = allocate_template_marks(blueprint)
        if assessment.shuffle_questions:
            marks_by_difficulty = {
                difficulty: template_marks[blueprint.index(difficulty)]
                for difficulty in set(blueprint)
            }
            for item in normalized:
                difficulty = record_by_id[item["question_id"]].difficulty
                item["marks"] = marks_by_difficulty[difficulty]
        else:
            for index, item in enumerate(
                sorted(normalized, key=lambda value: value["question_order"])
            ):
                item["marks"] = template_marks[index]
        return sorted(normalized, key=lambda item: item["question_order"])

    @staticmethod
    def _assert_assessment_language_coverage(
        assessment_languages: list[str],
        questions: list[QuestionBankQuestionModel],
    ) -> None:
        required = set(normalize_languages(assessment_languages))
        incompatible: list[str] = []
        for question in questions:
            supported = set(normalize_languages(question.supported_languages or []))
            missing = sorted(required - supported)
            if missing:
                incompatible.append(f"{question.title} (missing {', '.join(missing)})")
        if incompatible:
            raise AssessmentValidationError(
                "Every assessment language must be supported by every question: "
                + "; ".join(incompatible)
            )

    def _question_bank_records(
        self,
        recruiter_uid: str,
        question_ids: list[str],
    ) -> list[QuestionBankQuestionModel]:
        if not question_ids:
            return []
        try:
            return self._repository.load_question_bank_records(
                recruiter_uid=recruiter_uid,
                question_ids=question_ids,
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError(
                "Unable to read assessment questions"
            ) from exc

    def _slot_candidate_assignments(
        self,
        recruiter_uid: str,
        slot_id: str,
    ) -> list[SlotCandidateRecord]:
        assignments = self._slot_assignment_models(recruiter_uid, slot_id)
        candidates = self._candidate_by_ids([item.candidate_id for item in assignments])
        return [
            SlotCandidateRecord(
                candidate_assessment_id=item.id,
                candidate_id=item.candidate_id,
                name=candidates[item.candidate_id].full_name
                if item.candidate_id in candidates
                else "Candidate",
                email=candidates[item.candidate_id].email
                if item.candidate_id in candidates
                else "",
                external_id=candidates[item.candidate_id].external_id
                if item.candidate_id in candidates
                else "",
                invite_status=InviteEmailStatus(item.email_status),
                assessment_status=CandidateAssessmentStatus(item.status),
                hidden_checks_used=item.hidden_checks_used,
                submission_tag=item.submission_tag,
                submission_message=item.submission_message,
                started_at=item.started_at,
                submitted_at=item.submitted_at,
                last_activity_at=item.last_activity_at,
                total_score=item.total_score,
                percentage=item.percentage,
                rank=item.rank,
            )
            for item in assignments
        ]

    def _slot_assignment_models(
        self,
        recruiter_uid: str,
        slot_id: str,
    ) -> list[CandidateAssessmentModel]:
        try:
            return self._repository.list_slot_assignments(
                recruiter_uid=recruiter_uid,
                slot_id=slot_id,
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError(
                "Unable to read slot assignments"
            ) from exc

    def _candidate_by_ids(self, candidate_ids: list[str]) -> dict[str, CandidateModel]:
        if not candidate_ids:
            return {}
        try:
            return self._repository.candidates_by_ids(candidate_ids)
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError("Unable to read candidates") from exc

    def _get_or_create_candidate(
        self,
        recruiter_uid: str,
        name: str,
        email: str,
        external_id: str,
    ) -> CandidateModel:
        try:
            candidate = self._repository.get_candidate_by_email(
                recruiter_uid=recruiter_uid,
                email=email,
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError("Unable to read candidate") from exc
        if candidate is not None:
            candidate.full_name = name
            candidate.external_id = external_id
            return candidate

        candidate = CandidateModel(
            recruiter_uid=recruiter_uid,
            full_name=name,
            email=email,
            external_id=external_id,
        )
        self._repository.add(candidate)
        self._repository.flush()
        return candidate

    def _candidate_assessments_for_slot_ids(
        self,
        slot_ids: list[str],
    ) -> dict[str, list[CandidateAssessmentModel]]:
        if not slot_ids:
            return {}
        try:
            return self._repository.candidate_assignments_for_slot_ids(slot_ids)
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError(
                "Unable to read slot assignments"
            ) from exc

    def _load_candidate_context_by_invite(
        self, raw_token: str
    ) -> CandidateAssessmentContext:
        token_hash = CandidateSessionService.hash_invite_token(
            raw_token,
            self._settings.invite_token_pepper,
        )
        try:
            assignment = self._repository.get_assignment_by_invite_hash(token_hash)
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError(
                "Unable to verify candidate invite"
            ) from exc
        if assignment is None:
            raise CandidateInviteError("Invalid or expired invite link")
        return self._load_candidate_context_by_assignment(assignment)

    def _load_candidate_context_by_claims(
        self,
        claims: CandidateSessionClaims,
    ) -> CandidateAssessmentContext:
        try:
            assignment = self._repository.get_assignment_by_id(
                claims.candidate_assessment_id
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError(
                "Unable to load candidate session"
            ) from exc
        if assignment is None:
            raise CandidateInviteError(
                "Candidate assessment session is no longer available"
            )
        if (
            assignment.id != claims.candidate_assessment_id
            or assignment.candidate_id != claims.candidate_id
        ):
            raise CandidateInviteError("Candidate session does not match the invite")
        return self._load_candidate_context_by_assignment(assignment)

    def _load_candidate_context_by_assignment(
        self,
        assignment: CandidateAssessmentModel,
    ) -> CandidateAssessmentContext:
        try:
            assessment, slot, candidate = self._repository.get_candidate_context_models(
                assessment_id=assignment.assessment_id,
                slot_id=assignment.slot_id,
                candidate_id=assignment.candidate_id,
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError(
                "Unable to read candidate assessment context"
            ) from exc
        if assessment is None or slot is None or candidate is None:
            raise CandidateInviteError("Candidate assessment context is incomplete")
        mappings = self._assessment_mappings(assessment.id)
        questions = self._question_bank_records(
            assessment.recruiter_uid,
            [item.question_id for item in mappings],
        )
        submission_map = self._submissions_for_candidate_assessment(assignment.id)
        return CandidateAssessmentContext(
            assessment=assessment,
            slot=slot,
            candidate=candidate,
            candidate_assessment=assignment,
            questions=questions,
            mappings=mappings,
            submissions=submission_map,
        )

    def _submissions_for_candidate_assessment(
        self,
        candidate_assessment_id: str,
    ) -> dict[str, SubmissionModel]:
        try:
            return self._repository.submissions_for_candidate_assessment(
                candidate_assessment_id
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError("Unable to read submissions") from exc

    def _candidate_can_start(self, context: CandidateAssessmentContext) -> bool:
        now = datetime.now(UTC)
        if context.assessment.status == AssessmentStatus.ARCHIVED.value:
            return False
        if context.candidate_assessment.status in {
            CandidateAssessmentStatus.SUBMITTED.value,
            CandidateAssessmentStatus.AUTO_SUBMITTED.value,
            CandidateAssessmentStatus.REVOKED.value,
        }:
            return False
        slot_status = effective_slot_status(context.slot)
        if (
            slot_status == SlotStatus.PAUSED
            and context.candidate_assessment.status
            == CandidateAssessmentStatus.IN_PROGRESS.value
        ):
            return True
        if slot_status != SlotStatus.ACTIVE:
            return False
        return not (
            now < context.slot.start_at.astimezone(UTC)
            or now > context.slot.end_at.astimezone(UTC)
        )

    def _ensure_submission_rows(self, context: CandidateAssessmentContext) -> None:
        question_by_id = {item.id: item for item in context.questions}
        for mapping in context.mappings:
            if mapping.question_id in context.submissions:
                continue
            question = question_by_id.get(mapping.question_id)
            default_submission_language = default_language(
                question.supported_languages if question is not None else None
            )
            submission = SubmissionModel(
                candidate_assessment_id=context.candidate_assessment.id,
                assessment_id=context.assessment.id,
                question_id=mapping.question_id,
                source_language=default_submission_language,
                draft_code="",
                final_code="",
                status=SubmissionStatus.DRAFT.value,
            )
            self._repository.add(submission)
            self._repository.flush()
            context.submissions[mapping.question_id] = submission

    def _ordered_question_records(
        self,
        context: CandidateAssessmentContext,
    ) -> list[CandidateQuestionRecord]:
        question_by_id = {item.id: item for item in context.questions}
        ordered = []
        for display_order, mapping in enumerate(
            self._candidate_question_mappings(context),
            start=1,
        ):
            question = question_by_id.get(mapping.question_id)
            if question is None:
                continue
            ordered.append(
                CandidateQuestionRecord(
                    id=question.id,
                    title=question.title,
                    difficulty=DifficultyLevel(question.difficulty),
                    problem_statement=question.problem_statement,
                    constraints=question.constraints,
                    input_format=question.input_format,
                    output_format=question.output_format,
                    answer_validation_mode=AnswerValidationMode(
                        normalize_answer_validation_mode(
                            getattr(question, "answer_validation_mode", "exact"),
                        )
                    ),
                    output_checker_explanation=(
                        getattr(question, "output_checker_explanation", "") or ""
                    ).strip()
                    or default_checker_explanation(
                        normalize_answer_validation_mode(
                            getattr(question, "answer_validation_mode", "exact"),
                        ),
                    ),
                    sample_test_cases=[
                        TestCase.model_validate(item)
                        for item in (question.sample_test_cases or [])
                    ],
                    supported_languages=list(question.supported_languages or []),
                    question_order=display_order,
                    marks=mapping.marks,
                    is_mandatory=mapping.is_mandatory,
                )
            )
        return ordered

    def _candidate_question_mappings(
        self,
        context: CandidateAssessmentContext,
    ) -> list[AssessmentQuestionModel | DeliveredQuestionMapping]:
        ordered_mappings = sorted(
            context.mappings,
            key=lambda item: getattr(item, "question_order", 0),
        )
        typed_ordered_mappings: list[
            AssessmentQuestionModel | DeliveredQuestionMapping
        ] = list(ordered_mappings)
        question_limit = int(
            getattr(context.assessment, "question_count_per_candidate", 0) or 0
        )
        should_randomize = bool(getattr(context.assessment, "shuffle_questions", False))
        if question_limit <= 0:
            return typed_ordered_mappings
        blueprint = list(getattr(context.assessment, "difficulty_blueprint", []) or [])
        if len(blueprint) != question_limit:
            raise AssessmentValidationError(
                "Assessment difficulty template is incomplete"
            )
        template_marks = allocate_template_marks(blueprint)
        if not should_randomize:
            return [
                self._delivered_mapping(mapping, index + 1, template_marks[index])
                for index, mapping in enumerate(ordered_mappings[:question_limit])
            ]
        question_by_id = {question.id: question for question in context.questions}
        buckets: dict[str, list[AssessmentQuestionModel]] = {
            item.value: [] for item in DifficultyLevel
        }
        for mapping in ordered_mappings:
            question = question_by_id.get(mapping.question_id)
            if question is not None:
                buckets.setdefault(question.difficulty, []).append(mapping)
        randomizer = Random(context.candidate_assessment.id)
        for bucket in buckets.values():
            randomizer.shuffle(bucket)
        selected: list[AssessmentQuestionModel | DeliveredQuestionMapping] = []
        for index, difficulty in enumerate(blueprint):
            bucket = buckets.get(difficulty, [])
            if not bucket:
                raise AssessmentValidationError(
                    "Question pool cannot satisfy the difficulty template"
                )
            selected.append(
                self._delivered_mapping(
                    bucket.pop(),
                    index + 1,
                    template_marks[index],
                )
            )
        return selected

    @staticmethod
    def _delivered_mapping(
        mapping: AssessmentQuestionModel,
        question_order: int,
        marks: int,
    ) -> DeliveredQuestionMapping:
        return DeliveredQuestionMapping(
            question_id=mapping.question_id,
            question_order=question_order,
            marks=marks,
            is_mandatory=mapping.is_mandatory,
        )

    def _assert_candidate_can_edit(self, context: CandidateAssessmentContext) -> None:
        slot_status = effective_slot_status(context.slot)
        if slot_status == SlotStatus.PAUSED:
            raise AssessmentValidationError(
                "This assessment is temporarily paused by the recruiter"
            )
        self._auto_submit_if_expired(context)
        if context.candidate_assessment.status in {
            CandidateAssessmentStatus.SUBMITTED.value,
            CandidateAssessmentStatus.AUTO_SUBMITTED.value,
        }:
            raise AssessmentValidationError("Assessment has already been submitted")
        if slot_status != SlotStatus.ACTIVE:
            raise AssessmentValidationError("This assessment is not active")
        if context.candidate_assessment.deadline_at and datetime.now(
            UTC
        ) > context.candidate_assessment.deadline_at.astimezone(UTC):
            raise AssessmentValidationError("Assessment time has expired")

    def _get_submission_for_question(
        self,
        context: CandidateAssessmentContext,
        question_id: str,
    ) -> SubmissionModel:
        self._ensure_submission_rows(context)
        submission = context.submissions.get(question_id)
        if submission is None:
            raise AssessmentValidationError("Question is not part of this assessment")
        return submission

    @staticmethod
    def _assert_draft_version(
        submission: SubmissionModel,
        base_version: int | None,
    ) -> None:
        if base_version is not None and base_version != submission.version:
            raise AssessmentValidationError(
                "This draft changed in another tab. Reload before saving again."
            )

    @staticmethod
    def _candidate_safe_submission_result(
        submission: SubmissionModel,
    ) -> dict[str, object]:
        result = dict(submission.final_hidden_result or {})
        passed_count = int(str(result.get("passed_count") or 0))
        total_count = int(str(result.get("total_count") or 0))
        return {
            "status": submission.status,
            "passed_count": passed_count,
            "total_count": total_count,
            "passed": total_count > 0 and passed_count == total_count,
        }

    def _question_by_id(
        self,
        context: CandidateAssessmentContext,
        question_id: str,
    ) -> QuestionBankQuestionModel:
        for question in context.questions:
            if question.id == question_id:
                return question
        raise AssessmentValidationError("Question is not part of this assessment")

    def _validate_question_language(
        self,
        context: CandidateAssessmentContext,
        question_id: str,
        language: str,
    ) -> None:
        question = self._question_by_id(context, question_id)
        normalized = language.strip().lower()
        allowed = {
            item.strip().lower()
            for item in (
                question.supported_languages
                or context.assessment.supported_languages
                or []
            )
            if item.strip()
        }
        if normalized not in allowed:
            raise AssessmentValidationError(
                f"Language {normalized} is not allowed for this question"
            )

    def _auto_submit_if_expired(self, context: CandidateAssessmentContext) -> None:
        slot_status = effective_slot_status(context.slot)
        if slot_status == SlotStatus.PAUSED:
            return
        deadline = context.candidate_assessment.deadline_at
        if deadline is None and slot_status != SlotStatus.CLOSED:
            return
        if context.candidate_assessment.status in {
            CandidateAssessmentStatus.SUBMITTED.value,
            CandidateAssessmentStatus.AUTO_SUBMITTED.value,
        }:
            return
        if (
            slot_status != SlotStatus.CLOSED
            and deadline is not None
            and datetime.now(UTC) <= deadline.astimezone(UTC)
        ):
            return
        self.submit_assessment(
            CandidateSessionClaims(
                candidate_assessment_id=context.candidate_assessment.id,
                assessment_id=context.assessment.id,
                slot_id=context.slot.id,
                candidate_id=context.candidate.id,
                exp=int(datetime.now(UTC).timestamp()) + 60,
            ),
            CandidateSubmitRequest(answers=[]),
            auto_submit=True,
        )

    @staticmethod
    def _candidate_time_remaining_seconds(context: CandidateAssessmentContext) -> int:
        """Return a pause-aware server projection of candidate time remaining."""

        deadline = context.candidate_assessment.deadline_at
        if deadline is None:
            return 0
        reference = datetime.now(UTC)
        if (
            effective_slot_status(context.slot, now=reference) == SlotStatus.PAUSED
            and context.slot.paused_at is not None
        ):
            reference = context.slot.paused_at.astimezone(UTC)
        return max(0, int((deadline.astimezone(UTC) - reference).total_seconds()))

    @staticmethod
    def _assert_slot_accepts_invites(slot: AssessmentSlotModel) -> None:
        """Prevent invite delivery for non-operational slot states."""

        status = effective_slot_status(slot)
        if status not in {SlotStatus.SCHEDULED, SlotStatus.ACTIVE}:
            raise CandidateInviteError(
                "Invites can only be sent for scheduled or active test slots"
            )

    def _submitted_question_counts(
        self,
        candidate_assessment_ids: list[str],
    ) -> dict[str, int]:
        if not candidate_assessment_ids:
            return {}
        try:
            return self._repository.submission_counts_by_candidate_assessment(
                candidate_assessment_ids
            )
        except SQLAlchemyError as exc:
            raise AssessmentStoreUnavailableError("Unable to read submissions") from exc


def dispatch_slot_invites_background(
    *,
    settings: Settings,
    recruiter_uid: str,
    slot_id: str,
    candidate_assessment_id: str | None = None,
) -> None:
    """Background-task entrypoint for assessment invite delivery."""

    from data.clients.database import create_session_factory

    session = create_session_factory(settings)()
    try:
        service = AssessmentService(session, settings)
        service.send_slot_invites(
            recruiter_uid=recruiter_uid,
            slot_id=slot_id,
            candidate_assessment_id=candidate_assessment_id,
        )
    finally:
        session.close()
