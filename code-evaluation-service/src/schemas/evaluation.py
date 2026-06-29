"""Schemas for evaluation jobs, scoring, and recruiter reports."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class EvaluationJobStatus(StrEnum):
    """Lifecycle states for an evaluation job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExecutionVerdict(StrEnum):
    """Normalized verdicts consumed from the execution service."""

    ACCEPTED = "accepted"
    WRONG_ANSWER = "wrong_answer"
    COMPILE_ERROR = "compile_error"
    RUNTIME_ERROR = "runtime_error"
    TIME_LIMIT_EXCEEDED = "time_limit_exceeded"
    MEMORY_LIMIT_EXCEEDED = "memory_limit_exceeded"
    EXECUTION_FAILURE = "execution_failure"


class ScoringWeights(BaseModel):
    """Assessment-level final score weights."""

    test_case_weight: float = Field(default=60, ge=0, le=100)
    coding_weight: float = Field(default=20, ge=0, le=100)
    ai_weight: float = Field(default=20, ge=0, le=100)

    @model_validator(mode="after")
    def require_total_weight(self) -> "ScoringWeights":
        """Keep final score math explicit and predictable."""

        total = self.test_case_weight + self.coding_weight + self.ai_weight
        if round(total, 2) != 100:
            raise ValueError("Scoring weights must add up to 100.")
        return self


class HiddenExecutionResult(BaseModel):
    """One hidden execution result from the execution service."""

    question_id: str = Field(min_length=1, max_length=80)
    question_title: str = Field(min_length=1, max_length=160)
    test_case_id: str = Field(min_length=1, max_length=80)
    passed: bool
    verdict: ExecutionVerdict
    execution_time_ms: float | None = Field(default=None, ge=0)
    memory_kb: int | None = Field(default=None, ge=0)
    points: float = Field(default=1, gt=0, le=100)
    mandatory: bool = False
    input: str = Field(default="", max_length=20_000)
    expected_output: str = Field(default="", max_length=20_000)
    actual_output: str = Field(default="", max_length=20_000)
    message: str = Field(default="", max_length=2_000)


class QuestionTestCaseResult(BaseModel):
    """Printable hidden test case evidence for one question."""

    test_case_id: str
    passed: bool
    verdict: ExecutionVerdict
    execution_time_ms: float | None = None
    memory_kb: int | None = None
    points: float
    mandatory: bool
    input: str = ""
    expected_output: str = ""
    actual_output: str = ""
    message: str = ""


class AICodeQualitySignal(BaseModel):
    """Structured AI code-quality output stored with a scorecard."""

    score: float = Field(ge=0, le=100)
    approach: str = Field(min_length=1, max_length=600)
    time_complexity: str = Field(min_length=1, max_length=80)
    space_complexity: str = Field(min_length=1, max_length=80)
    readability: str = Field(min_length=1, max_length=500)
    maintainability: str = Field(min_length=1, max_length=500)
    strengths: list[str] = Field(default_factory=list, max_length=6)
    weaknesses: list[str] = Field(default_factory=list, max_length=6)
    improvements: list[str] = Field(default_factory=list, max_length=6)


class EvaluationJobCreateRequest(BaseModel):
    """Create and process a candidate evaluation job."""

    assessment_id: str = Field(min_length=1, max_length=80)
    candidate_assessment_id: str = Field(min_length=1, max_length=80)
    candidate_id: str = Field(min_length=1, max_length=80)
    candidate_name: str = Field(min_length=1, max_length=120)
    candidate_email: str = Field(min_length=3, max_length=180)
    submission_id: str = Field(min_length=1, max_length=80)
    language: str = Field(min_length=1, max_length=40)
    source_code: str = Field(min_length=1, max_length=200_000)
    hidden_results: list[HiddenExecutionResult] = Field(min_length=1, max_length=500)
    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    ai_quality: AICodeQualitySignal | None = None
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    time_taken_seconds: int | None = Field(default=None, ge=0)


class QuestionEvaluationBreakdown(BaseModel):
    """Question-level hidden test aggregation."""

    question_id: str
    question_title: str
    language: str = ""
    submitted_code: str = ""
    passed_count: int
    total_count: int
    earned_points: float
    total_points: float
    score: float
    mandatory_failed: bool
    test_cases: list[QuestionTestCaseResult] = Field(default_factory=list)


class EvaluationScores(BaseModel):
    """Normalized candidate scores."""

    test_case_score: float
    coding_score: float
    ai_score: float
    final_score: float
    percentage: float


class CandidateEvaluationSummary(BaseModel):
    """Recruiter-facing candidate scorecard row."""

    assessment_id: str
    candidate_assessment_id: str
    candidate_id: str
    candidate_name: str
    candidate_email: str
    submission_id: str
    language: str
    status: EvaluationJobStatus
    rank: int | None = None
    scores: EvaluationScores
    hidden_passed: int
    hidden_total: int
    total_execution_time_ms: float
    peak_memory_kb: int
    ai_quality: AICodeQualitySignal
    question_breakdown: list[QuestionEvaluationBreakdown]
    submitted_at: datetime
    evaluated_at: datetime | None = None
    time_taken_seconds: int | None = None


class EvaluationJobResponse(BaseModel):
    """Evaluation job status and result."""

    job_id: str
    assessment_id: str
    candidate_assessment_id: str
    status: EvaluationJobStatus
    attempt_count: int
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None
    result: CandidateEvaluationSummary | None = None


class AssessmentEvaluationOverview(BaseModel):
    """Dashboard summary for an assessment evaluation workspace."""

    assessment_id: str
    title: str
    total_candidates: int
    completed_candidates: int
    pending_jobs: int
    failed_jobs: int
    average_score: float
    average_test_case_score: float
    average_coding_score: float
    average_ai_score: float
    pass_rate: float
    highest_score: float
    report_status: str
    generated_at: datetime


class AssessmentEvaluationDashboard(BaseModel):
    """Complete evaluation dashboard payload."""

    overview: AssessmentEvaluationOverview
    leaderboard: list[CandidateEvaluationSummary]
    jobs: list[EvaluationJobResponse]


class AssessmentReportResponse(BaseModel):
    """Overall report payload for one assessment."""

    overview: AssessmentEvaluationOverview
    leaderboard: list[CandidateEvaluationSummary]
    generated_at: datetime
    download_label: str


class CandidateReportResponse(BaseModel):
    """Candidate scorecard report payload."""

    assessment_id: str
    candidate_assessment_id: str
    candidate: CandidateEvaluationSummary
    generated_at: datetime
    download_label: str


class TestReportRequest(BaseModel):
    """Trusted test-batch context supplied by the assessment service."""

    test_id: str = Field(min_length=1, max_length=80)
    test_title: str = Field(min_length=1, max_length=180)
    timezone_name: str = Field(default="UTC", max_length=80)
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    candidate_count: int = Field(ge=0)
    submitted_count: int = Field(ge=0)
    candidate_assessment_ids: list[str] = Field(default_factory=list, max_length=5000)


class TestReportResponse(BaseModel):
    """Printable evaluation report for one scheduled test batch."""

    assessment_id: str
    test_id: str
    test_title: str
    timezone_name: str
    scheduled_start: datetime | None = None
    scheduled_end: datetime | None = None
    submitted_count: int
    overview: AssessmentEvaluationOverview
    leaderboard: list[CandidateEvaluationSummary]
    generated_at: datetime
    download_label: str


class RetryEvaluationResponse(BaseModel):
    """Result returned when a failed job is retried."""

    job: EvaluationJobResponse
    message: str


class EvaluationWorkerRunResponse(BaseModel):
    """Summary returned after processing queued evaluation jobs."""

    processed_count: int
    completed_count: int
    failed_count: int
    jobs: list[EvaluationJobResponse]
