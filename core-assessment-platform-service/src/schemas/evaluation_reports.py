"""Typed recruiter-facing contracts returned by the evaluation service."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class EvaluationJobStatus(StrEnum):
    """Lifecycle states for an evaluation job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class EvaluationScores(BaseModel):
    """Normalized candidate scores."""

    test_case_score: float
    coding_score: float
    ai_score: float
    final_score: float
    percentage: float


class EvaluationResult(BaseModel):
    """Candidate scorecard subset consumed from the evaluation service."""

    rank: int | None = None
    scores: EvaluationScores
    hidden_passed: int
    hidden_total: int
    total_execution_time_ms: float
    peak_memory_kb: int
    ai_quality: dict[str, Any] = Field(default_factory=dict)
    question_breakdown: list[dict[str, Any]] = Field(default_factory=list)


class EvaluationJobResult(BaseModel):
    """Evaluation job response consumed by the core service."""

    job_id: str
    assessment_id: str
    candidate_assessment_id: str
    status: str
    attempt_count: int
    error_message: str | None = None
    result: EvaluationResult | None = None


class CandidateEvaluationScorecard(BaseModel):
    """Leaderboard scorecard subset consumed by the core service."""

    candidate_assessment_id: str
    rank: int | None = None
    scores: EvaluationScores


class QuestionTestCaseResult(BaseModel):
    """Hidden test evidence visible only to an authorized recruiter."""

    test_case_id: str
    passed: bool
    verdict: str
    execution_time_ms: float | None = None
    memory_kb: int | None = None
    points: float
    mandatory: bool
    input: str = ""
    expected_output: str = ""
    actual_output: str = ""
    message: str = ""
    case_category: str = ""


class AICodeQualitySignal(BaseModel):
    """Structured AI code-quality review."""

    score: float
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    approach: str
    time_complexity: str
    space_complexity: str
    readability: str
    maintainability: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)


class QuestionEvaluationBreakdown(BaseModel):
    """Question-level score, source, and hidden-test evidence."""

    question_id: str
    question_title: str
    language: str = ""
    submitted_code: str = ""
    evaluation_status: str = "evaluated"
    passed_count: int
    total_count: int
    earned_points: float
    total_points: float
    score: float
    assigned_marks: float = 0
    earned_marks: float = 0
    test_case_score: float = 0
    coding_score: float = 0
    ai_score: float = 0
    ai_quality: AICodeQualitySignal | None = None
    difficulty: str = ""
    tags: list[str] = Field(default_factory=list)
    problem_statement: str = ""
    input_format: str = ""
    output_format: str = ""
    constraints: str = ""
    suggested_solution: str = ""
    suggested_improvement_notes: list[str] = Field(default_factory=list)
    mandatory_failed: bool
    test_cases: list[QuestionTestCaseResult] = Field(default_factory=list)


class ScoringWeights(BaseModel):
    """Assessment score weights returned by the evaluation service."""

    test_case_weight: float = 60
    coding_weight: float = 20
    ai_weight: float = 20


class CandidateActivitySignal(BaseModel):
    """Candidate timing context, when available."""

    started_at: datetime | None = None
    submitted_at: datetime | None = None
    total_time_seconds: int | None = None
    question_time_seconds: dict[str, int] = Field(default_factory=dict)


class CandidateIntegritySignal(BaseModel):
    """Optional proctoring and integrity signals."""

    proctoring_mode: str = ""
    tab_switches: int | None = None
    copy_paste_count: int | None = None
    fullscreen_exits: int | None = None
    suspicious_activity: list[str] = Field(default_factory=list)
    plagiarism_similarity_score: float | None = None


class CandidateEvaluationSummary(BaseModel):
    """Complete recruiter-facing candidate scorecard."""

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
    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    total_execution_time_ms: float
    peak_memory_kb: int
    ai_quality: AICodeQualitySignal
    question_breakdown: list[QuestionEvaluationBreakdown]
    activity: CandidateActivitySignal | None = None
    integrity: CandidateIntegritySignal | None = None
    submitted_at: datetime
    evaluated_at: datetime | None = None
    time_taken_seconds: int | None = None


class CandidateBenchmarkContext(BaseModel):
    """Assessment-level context for one candidate report."""

    candidate_rank: int | None = None
    total_candidates: int = 0
    average_score: float | None = None
    average_completion_time_seconds: int | None = None
    percentile: float | None = None


class EvaluationJobResponse(BaseModel):
    """Evaluation job status shown in the recruiter pipeline."""

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
    """Assessment-wide evaluation metrics."""

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
    """Authenticated recruiter evaluation workspace payload."""

    overview: AssessmentEvaluationOverview
    leaderboard: list[CandidateEvaluationSummary]
    jobs: list[EvaluationJobResponse]


class AssessmentReportResponse(BaseModel):
    """Assessment report metadata and leaderboard."""

    overview: AssessmentEvaluationOverview
    leaderboard: list[CandidateEvaluationSummary]
    generated_at: datetime
    download_label: str


class CandidateReportResponse(BaseModel):
    """Candidate scorecard report payload."""

    assessment_id: str
    candidate_assessment_id: str
    candidate: CandidateEvaluationSummary
    benchmark: CandidateBenchmarkContext | None = None
    generated_at: datetime
    download_label: str


class RetryEvaluationResponse(BaseModel):
    """Result of retrying a failed evaluation job."""

    job: EvaluationJobResponse
    message: str
