"""Assessment, slot, candidate, and monitoring schemas."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from schemas.question_bank import DifficultyLevel


class AssessmentStatus(StrEnum):
    """Assessment template lifecycle."""

    AVAILABLE = "available"
    SCHEDULED = "scheduled"
    LIVE = "live"
    ARCHIVED = "archived"


class SlotStatus(StrEnum):
    """Assessment slot lifecycle."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class HiddenFeedbackMode(StrEnum):
    """Allowed hidden feedback configurations."""

    NONE = "none"
    SUMMARY = "summary"


class InviteEmailStatus(StrEnum):
    """Invite delivery status."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class CandidateAssessmentStatus(StrEnum):
    """Candidate runtime state."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    AUTO_SUBMITTED = "auto_submitted"
    REVOKED = "revoked"


class SubmissionStatus(StrEnum):
    """Per-question submission state."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    AUTO_SUBMITTED = "auto_submitted"
    PENDING_EVALUATION = "pending_evaluation"
    SKIPPED_EVALUATION = "skipped_evaluation"


class AssessmentQuestionInput(BaseModel):
    """Question configuration payload for one assessment question."""

    question_id: str = Field(min_length=1)
    question_order: int = Field(ge=1)
    marks: int = Field(ge=1, le=1_000)
    is_mandatory: bool = True


class AssessmentCreateRequest(BaseModel):
    """Payload to create an assessment template."""

    title: str = Field(min_length=3, max_length=180)
    description: str = ""
    instructions: str = ""
    duration_minutes: int = Field(default=60, ge=15, le=360)
    passing_score: float = Field(default=40.0, ge=0.0, le=100.0)
    test_case_score_weight: float = Field(default=60.0, ge=0.0, le=100.0)
    coding_score_weight: float = Field(default=20.0, ge=0.0, le=100.0)
    ai_score_weight: float = Field(default=20.0, ge=0.0, le=100.0)
    allow_resume: bool = True
    shuffle_questions: bool = False
    question_count_per_candidate: int = Field(default=0, ge=0, le=100)
    difficulty_blueprint: list[DifficultyLevel] = Field(default_factory=list)
    show_score_to_candidate: bool = False
    proctoring_mode: str = Field(default="basic", min_length=3, max_length=30)
    hidden_feedback_mode: HiddenFeedbackMode = HiddenFeedbackMode.NONE
    max_hidden_checks: int = Field(default=0, ge=0, le=20)
    hidden_check_cooldown_seconds: int = Field(default=5, ge=0, le=86_400)
    supported_languages: list[str] = Field(
        default_factory=lambda: ["python", "java", "cpp", "c"],
    )
    status: AssessmentStatus = AssessmentStatus.AVAILABLE


class AssessmentUpdateRequest(BaseModel):
    """Patch payload for an assessment template."""

    title: str | None = Field(default=None, min_length=3, max_length=180)
    description: str | None = None
    instructions: str | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=360)
    passing_score: float | None = Field(default=None, ge=0.0, le=100.0)
    test_case_score_weight: float | None = Field(default=None, ge=0.0, le=100.0)
    coding_score_weight: float | None = Field(default=None, ge=0.0, le=100.0)
    ai_score_weight: float | None = Field(default=None, ge=0.0, le=100.0)
    allow_resume: bool | None = None
    shuffle_questions: bool | None = None
    question_count_per_candidate: int | None = Field(default=None, ge=0, le=100)
    difficulty_blueprint: list[DifficultyLevel] | None = None
    show_score_to_candidate: bool | None = None
    proctoring_mode: str | None = Field(default=None, min_length=3, max_length=30)
    hidden_feedback_mode: HiddenFeedbackMode | None = None
    max_hidden_checks: int | None = Field(default=None, ge=0, le=20)
    hidden_check_cooldown_seconds: int | None = Field(default=None, ge=0, le=86_400)
    supported_languages: list[str] | None = None
    status: AssessmentStatus | None = None


class AssessmentQuestionRecord(BaseModel):
    """Expanded question configuration shown in assessment responses."""

    question_id: str
    title: str
    difficulty: DifficultyLevel
    tags: list[str] = Field(default_factory=list)
    question_order: int
    marks: int
    is_mandatory: bool
    supported_languages: list[str] = Field(default_factory=list)


class AssessmentSlotSummaryRecord(BaseModel):
    """Assessment-library summary for one test slot."""

    id: str
    title: str
    start_at: datetime
    end_at: datetime
    duration_minutes: int = 60
    timezone_name: str = "Asia/Kolkata"
    timezone_offset_minutes: int = 330
    status: SlotStatus
    effective_status: SlotStatus = SlotStatus.SCHEDULED
    seconds_until_start: int = 0
    accepting_closes_in_seconds: int = 0
    candidate_count: int = 0
    submitted_count: int = 0


class AssessmentRecord(BaseModel):
    """Stored assessment template."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    recruiter_uid: str
    title: str
    description: str
    instructions: str
    duration_minutes: int
    passing_score: float
    test_case_score_weight: float
    coding_score_weight: float
    ai_score_weight: float
    allow_resume: bool
    shuffle_questions: bool
    question_count_per_candidate: int
    difficulty_blueprint: list[DifficultyLevel] = Field(default_factory=list)
    show_score_to_candidate: bool
    proctoring_mode: str
    hidden_feedback_mode: HiddenFeedbackMode
    max_hidden_checks: int
    hidden_check_cooldown_seconds: int
    supported_languages: list[str]
    status: AssessmentStatus
    questions: list[AssessmentQuestionRecord] = Field(default_factory=list)
    question_count: int = 0
    slots: list[AssessmentSlotSummaryRecord] = Field(default_factory=list)
    test_count: int = 0
    scheduled_test_count: int = 0
    live_test_count: int = 0
    created_at: datetime
    updated_at: datetime


class AssessmentListResponse(BaseModel):
    """Assessment list payload."""

    items: list[AssessmentRecord]
    total: int


class AssessmentQuestionAssignRequest(BaseModel):
    """Payload to set all assessment questions."""

    questions: list[AssessmentQuestionInput] = Field(default_factory=list)


class AssessmentSlotCreateRequest(BaseModel):
    """Payload to create a candidate test slot."""

    title: str = Field(min_length=3, max_length=180)
    start_at: datetime
    end_at: datetime
    duration_minutes: int = Field(default=60, ge=15, le=360)
    timezone_name: str = Field(default="Asia/Kolkata", max_length=80)
    timezone_offset_minutes: int = Field(default=330, ge=-720, le=840)
    instructions_override: str = ""
    status: SlotStatus = SlotStatus.SCHEDULED


class AssessmentSlotUpdateRequest(BaseModel):
    """Patch payload for a candidate test slot."""

    title: str | None = Field(default=None, min_length=3, max_length=180)
    start_at: datetime | None = None
    end_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=360)
    timezone_name: str | None = Field(default=None, max_length=80)
    timezone_offset_minutes: int | None = Field(default=None, ge=-720, le=840)
    instructions_override: str | None = None
    status: SlotStatus | None = None


class AssessmentSlotActionRequest(BaseModel):
    """Operational command for a running test slot."""

    action: str = Field(pattern="^(pause|continue|extend|close)$")
    extend_minutes: int = Field(default=0, ge=0, le=720)


class AssessmentSlotRecord(BaseModel):
    """Stored slot record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    assessment_id: str
    recruiter_uid: str
    title: str
    instructions_override: str
    start_at: datetime
    end_at: datetime
    duration_minutes: int = 60
    timezone_name: str = "Asia/Kolkata"
    timezone_offset_minutes: int = 330
    status: SlotStatus
    effective_status: SlotStatus = SlotStatus.SCHEDULED
    seconds_until_start: int = 0
    accepting_closes_in_seconds: int = 0
    is_accepting_responses: bool = False
    paused_at: datetime | None = None
    total_paused_seconds: int = 0
    candidate_count: int = 0
    submitted_count: int = 0
    created_at: datetime
    updated_at: datetime


class AssessmentSlotListResponse(BaseModel):
    """Slot list payload."""

    items: list[AssessmentSlotRecord]
    total: int


class CandidateCSVImportRequest(BaseModel):
    """CSV upload payload for slot candidates."""

    csv_text: str = Field(min_length=1, max_length=2_000_000)


class CandidateImportRowError(BaseModel):
    """One invalid row from a candidate CSV import."""

    row_number: int
    email: str = ""
    errors: list[str] = Field(default_factory=list)


class SlotCandidateRecord(BaseModel):
    """Candidate assignment shown in recruiter flows."""

    candidate_assessment_id: str
    candidate_id: str
    name: str
    email: str
    external_id: str = ""
    invite_status: InviteEmailStatus
    assessment_status: CandidateAssessmentStatus
    hidden_checks_used: int = 0
    submission_tag: str = ""
    submission_message: str = ""
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    last_activity_at: datetime | None = None
    total_score: float | None = None
    percentage: float | None = None
    rank: int | None = None


class CandidateImportResponse(BaseModel):
    """Candidate import outcome."""

    total_rows: int
    created_count: int
    failed_count: int
    created: list[SlotCandidateRecord] = Field(default_factory=list)
    errors: list[CandidateImportRowError] = Field(default_factory=list)


class SlotCandidateListResponse(BaseModel):
    """Recruiter-visible slot candidate list."""

    items: list[SlotCandidateRecord]
    total: int


class EvaluationBackfillCandidateResult(BaseModel):
    """Backfill outcome for one submitted candidate assessment."""

    candidate_assessment_id: str
    status: str
    message: str
    evaluation_job_id: str | None = None
    final_score: float | None = None
    rank: int | None = None


class EvaluationBackfillRequest(BaseModel):
    """Controls recruiter-triggered evaluation backfill behavior."""

    force: bool = False
    candidate_assessment_ids: list[str] = Field(default_factory=list)


class EvaluationBackfillResponse(BaseModel):
    """Summary of recruiter-triggered evaluation backfill."""

    assessment_id: str
    requested_count: int
    evaluated_count: int
    skipped_count: int
    failed_count: int
    results: list[EvaluationBackfillCandidateResult] = Field(default_factory=list)


class InviteDispatchRequest(BaseModel):
    """Invite-send target selection."""

    candidate_assessment_ids: list[str] = Field(default_factory=list)


class InviteDispatchResponse(BaseModel):
    """Invite-send command result."""

    slot_id: str
    requested: int
    sent: int
    failed: int
    message: str


class MonitoringCandidateRecord(BaseModel):
    """Recruiter monitoring row."""

    candidate_assessment_id: str
    name: str
    email: str
    status: CandidateAssessmentStatus
    started_at: datetime | None = None
    submitted_at: datetime | None = None
    last_activity_at: datetime | None = None
    questions_attempted: int = 0
    hidden_checks_used: int = 0
    submission_tag: str = ""
    submission_message: str = ""
    current_question_order: int = 1
    time_remaining_seconds: int | None = None


class MonitoringResponse(BaseModel):
    """Recruiter monitoring payload."""

    slot_id: str
    slot_title: str
    assessment_title: str
    items: list[MonitoringCandidateRecord] = Field(default_factory=list)
    total: int = 0


class ExecutionCaseResult(BaseModel):
    """One normalized execution result returned by the core service."""

    index: int
    input: str
    expected_output: str
    actual_output: str = ""
    status: str
    passed: bool
    stderr: str = ""
    compile_output: str = ""
    message: str = ""
    execution_time: str = ""
    memory_kb: int | None = None
    token: str = ""


class SampleRunResponse(BaseModel):
    """Visible sample run result."""

    question_id: str
    passed_count: int
    total_count: int
    results: list[ExecutionCaseResult] = Field(default_factory=list)


class HiddenExecutionCaseResult(BaseModel):
    """Candidate-safe hidden case evidence without test data or output."""

    index: int
    status: str
    passed: bool
    execution_time: str = ""
    error_type: str = ""


class HiddenCheckResponse(BaseModel):
    """Safe summary of a hidden test check."""

    question_id: str
    passed_count: int
    total_count: int
    remaining_attempts: int | None
    cooldown_remaining_seconds: int
    results: list[HiddenExecutionCaseResult] = Field(default_factory=list)


class SubmissionExecutionSummary(BaseModel):
    """Stored final hidden execution summary per question."""

    question_id: str
    passed_count: int
    total_count: int
    results: list[ExecutionCaseResult] = Field(default_factory=list)
