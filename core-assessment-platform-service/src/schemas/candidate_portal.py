"""Candidate invite, session, and portal schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas.assessments import (
    CandidateAssessmentStatus,
    HiddenCheckResponse,
    HiddenFeedbackMode,
    SampleRunResponse,
    SubmissionStatus,
)
from schemas.question_bank import AnswerValidationMode, DifficultyLevel, TestCase


class CandidateSessionClaims(BaseModel):
    """Decoded claims stored in the candidate session token."""

    candidate_assessment_id: str
    assessment_id: str
    slot_id: str
    candidate_id: str
    exp: int


class CandidateInviteVerificationRequest(BaseModel):
    """Raw opaque invite token from the email link."""

    token: str = Field(min_length=12)


class CandidateInviteVerificationResponse(BaseModel):
    """Preview shown before the candidate starts the test."""

    candidate_name: str
    candidate_email: str
    assessment_id: str
    assessment_title: str
    slot_id: str
    slot_title: str
    instructions: str
    duration_minutes: int
    start_at: datetime
    end_at: datetime
    allow_resume: bool
    status: CandidateAssessmentStatus
    can_start: bool


class CandidateStartRequest(BaseModel):
    """Request to begin or resume a candidate session."""

    token: str = Field(min_length=12)


class CandidateStartResponse(BaseModel):
    """Authenticated candidate session bootstrap payload."""

    session_token: str
    expires_at: datetime
    candidate_assessment_id: str
    status: CandidateAssessmentStatus


class CandidateQuestionRecord(BaseModel):
    """Visible assessment question shown to the candidate."""

    id: str
    title: str
    difficulty: DifficultyLevel
    problem_statement: str
    constraints: str
    input_format: str
    output_format: str
    answer_validation_mode: AnswerValidationMode = AnswerValidationMode.EXACT
    output_checker_explanation: str = ""
    sample_test_cases: list[TestCase] = Field(default_factory=list)
    supported_languages: list[str] = Field(default_factory=list)
    question_order: int
    marks: int
    is_mandatory: bool


class CandidateQuestionDraftRecord(BaseModel):
    """Latest saved code state for one question."""

    question_id: str
    source_language: str
    draft_code: str
    final_code: str
    status: SubmissionStatus
    last_saved_at: datetime | None = None
    submitted_at: datetime | None = None


class CandidateAssessmentPortalResponse(BaseModel):
    """Main candidate portal payload."""

    model_config = ConfigDict(from_attributes=True)

    candidate_name: str
    candidate_email: str
    candidate_assessment_id: str
    assessment_id: str
    assessment_title: str
    slot_id: str
    slot_title: str
    instructions: str
    duration_minutes: int
    allow_resume: bool
    proctoring_mode: str
    hidden_feedback_mode: HiddenFeedbackMode
    max_hidden_checks: int
    hidden_check_cooldown_seconds: int
    started_at: datetime | None = None
    deadline_at: datetime | None = None
    submitted_at: datetime | None = None
    status: CandidateAssessmentStatus
    current_question_order: int = 1
    time_remaining_seconds: int = 0
    tab_switch_count: int = 0
    copy_paste_count: int = 0
    fullscreen_exit_count: int = 0
    question_time_seconds: dict[str, int] = Field(default_factory=dict)
    supported_languages: list[str] = Field(default_factory=list)
    questions: list[CandidateQuestionRecord] = Field(default_factory=list)
    drafts: list[CandidateQuestionDraftRecord] = Field(default_factory=list)


class CandidateActivityEvidence(BaseModel):
    """Browser-observed report evidence persisted during the assessment."""

    tab_switch_count: int = Field(default=0, ge=0, le=1000)
    copy_paste_count: int = Field(default=0, ge=0, le=10000)
    fullscreen_exit_count: int = Field(default=0, ge=0, le=1000)
    question_time_seconds: dict[str, int] = Field(default_factory=dict)

    @field_validator("question_time_seconds")
    @classmethod
    def validate_question_times(cls, value: dict[str, int]) -> dict[str, int]:
        """Bound browser timing evidence before storing it."""

        if len(value) > 200:
            raise ValueError("Question timing cannot contain more than 200 entries")
        for question_id, seconds in value.items():
            if not question_id.strip() or len(question_id) > 80:
                raise ValueError("Question timing contains an invalid question ID")
            if isinstance(seconds, bool) or seconds < 0 or seconds > 604800:
                raise ValueError("Question timing seconds must be between 0 and 604800")
        return value


class CandidateCheckpointRequest(CandidateActivityEvidence):
    """Draft save request."""

    question_id: str = Field(min_length=1)
    source_code: str = Field(default="", max_length=200_000)
    language: str = Field(min_length=1, max_length=40)
    current_question_order: int = Field(ge=1)


class CandidateCheckpointResponse(BaseModel):
    """Checkpoint save result."""

    question_id: str
    saved_at: datetime
    status: SubmissionStatus


class CandidateCodeRunRequest(BaseModel):
    """Payload shared by sample-run and hidden-check."""

    question_id: str = Field(min_length=1)
    source_code: str = Field(min_length=1, max_length=200_000)
    language: str = Field(min_length=1, max_length=40)


class CandidateQuestionSubmitPayload(BaseModel):
    """Final code payload for one question."""

    question_id: str = Field(min_length=1)
    source_code: str = Field(default="", max_length=200_000)
    language: str = Field(min_length=1, max_length=40)


class CandidateSubmitRequest(CandidateActivityEvidence):
    """Final assessment submission."""

    answers: list[CandidateQuestionSubmitPayload] = Field(default_factory=list)
    auto_submit: bool = False
    submission_tag: str = Field(default="", max_length=60)
    submission_message: str = Field(default="", max_length=500)


class CandidateSubmitResponse(BaseModel):
    """Safe submission acknowledgement without hidden execution evidence."""

    candidate_assessment_id: str
    status: CandidateAssessmentStatus
    submitted_at: datetime
    pending_evaluation: bool
    submission_tag: str = ""
    submission_message: str = ""


__all__ = [
    "CandidateAssessmentPortalResponse",
    "CandidateCheckpointRequest",
    "CandidateCheckpointResponse",
    "CandidateCodeRunRequest",
    "CandidateInviteVerificationRequest",
    "CandidateInviteVerificationResponse",
    "CandidateQuestionDraftRecord",
    "CandidateQuestionRecord",
    "CandidateQuestionSubmitPayload",
    "CandidateSessionClaims",
    "CandidateStartRequest",
    "CandidateStartResponse",
    "CandidateSubmitRequest",
    "CandidateSubmitResponse",
    "HiddenCheckResponse",
    "SampleRunResponse",
]
