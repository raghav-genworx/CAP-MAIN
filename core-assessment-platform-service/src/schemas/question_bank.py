"""Question bank schemas."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DifficultyLevel(StrEnum):
    """Supported question difficulty levels."""

    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuestionStatus(StrEnum):
    """Supported question lifecycle states."""

    DRAFT = "draft"
    VALIDATED = "validated"
    BLOCKED = "blocked"
    ARCHIVED = "archived"


class QuestionCreationMode(StrEnum):
    """How the recruiter created the question."""

    MANUAL = "manual"
    AI_ASSISTED = "ai_assisted"


class QuestionVisibility(StrEnum):
    """Who may discover and use a question in an assessment."""

    PRIVATE = "private"
    PUBLIC = "public"


class MetadataStatus(StrEnum):
    """AI metadata classification lifecycle."""

    PENDING = "pending"
    CLASSIFIED = "classified"
    FAILED = "failed"


class DifficultySource(StrEnum):
    """Where the current difficulty value came from."""

    LEGACY = "legacy"
    AI = "ai"
    MANUAL_OVERRIDE = "manual_override"


class ValidationStatus(StrEnum):
    """Persisted execution validation lifecycle."""

    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    STALE = "stale"


class AnswerValidationMode(StrEnum):
    """How solution output should be judged for a question."""

    EXACT = "exact"
    UNORDERED = "unordered"
    FLOATING = "floating"
    MULTIPLE_VALID = "multiple_valid"
    CONSTRUCTIVE = "constructive"


class QuestionGroupStatus(StrEnum):
    """Supported question group lifecycle states."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class QuestionGenerationSettings(BaseModel):
    """High-level settings used to shape a single AI-generated question."""

    question_count: int = Field(default=1, ge=1, le=1)
    easy_count: int = Field(default=0, ge=0, le=1)
    medium_count: int = Field(default=0, ge=0, le=1)
    hard_count: int = Field(default=1, ge=0, le=1)
    topics: list[str] = Field(default_factory=list)
    supported_languages: list[str] = Field(default_factory=lambda: ["python"])
    interview_style: str = "DSA interview"
    company_style: str = "Enterprise"
    time_limit_minutes: int = Field(default=45, ge=1, le=180)
    candidate_solve_time_minutes: int = Field(default=45, ge=1, le=180)
    execution_time_limit_seconds: int = Field(default=2, ge=1, le=30)
    memory_limit_mb: int = Field(default=256, ge=64, le=2048)
    sample_test_case_count: int = Field(default=3, ge=1, le=10)
    hidden_test_case_count: int = Field(default=10, ge=1, le=50)
    edge_case_count: int = Field(default=4, ge=0, le=20)
    stress_test_count: int = Field(default=2, ge=0, le=10)


class TestCase(BaseModel):
    """Single test case definition."""

    model_config = ConfigDict(extra="forbid")

    input: str = Field(
        min_length=1,
        description="Exact raw STDIN text, with no labels or markdown.",
    )
    expected_output: str = Field(
        description="Exact deterministic raw STDOUT text, with no labels or markdown.",
    )
    is_sample: bool = Field(
        default=False,
        description="True only for public sample cases; false for hidden cases.",
    )
    explanation: str = Field(
        default="",
        description="Concise reason the expected output follows from the input.",
    )


class ReferenceSolutionArtifact(BaseModel):
    """Language-specific reference solution artifact."""

    model_config = ConfigDict(extra="forbid")

    language: str
    source_code: str
    validation_status: ValidationStatus = ValidationStatus.NOT_RUN
    time_complexity: str = ""
    space_complexity: str = ""
    notes: list[str] = Field(default_factory=list)


class SolutionValidationCaseResult(BaseModel):
    """Single execution result for a generated reference solution."""

    model_config = ConfigDict(extra="forbid")

    bucket: Literal["sample", "hidden"]
    index: int = Field(ge=1)
    passed: bool
    status: str
    stdin: str
    expected_output: str
    actual_output: str = ""
    stderr: str = ""
    compile_output: str = ""
    message: str = ""
    checker_message: str = ""
    token: str = ""
    execution_time: str = ""
    memory_kb: int | None = None


class SolutionValidationRound(BaseModel):
    """One adversarial test-vs-solution validation round."""

    model_config = ConfigDict(extra="forbid")

    round_number: int = Field(ge=1, le=4)
    status: Literal[
        "passed",
        "failed",
        "repaired",
        "solution_repaired",
        "testcase_repaired",
        "skipped",
    ]
    summary: str
    challenger_summary: str = ""
    repair_summary: str = ""
    repair_target: str = ""
    decision_summary: str = ""
    added_hidden_test_cases: list[TestCase] = Field(default_factory=list)
    passed_count: int = 0
    failed_count: int = 0
    results: list[SolutionValidationCaseResult] = Field(default_factory=list)


class SolutionValidationReport(BaseModel):
    """Aggregated execution validation status for a reference solution."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["not_run", "passed", "failed", "skipped", "stale"]
    summary: str
    passed_count: int = 0
    failed_count: int = 0
    sample_count: int = 0
    hidden_count: int = 0
    runner_notes: list[str] = Field(default_factory=list)
    results: list[SolutionValidationCaseResult] = Field(default_factory=list)
    rounds: list[SolutionValidationRound] = Field(default_factory=list)


class QuestionBase(BaseModel):
    """Common question fields."""

    title: str = Field(min_length=3, max_length=180)
    problem_statement: str = ""
    difficulty: DifficultyLevel = DifficultyLevel.MEDIUM
    topics: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    category: str = ""
    constraints: str = ""
    input_format: str = ""
    input_explanation: str = ""
    output_format: str = ""
    output_explanation: str = ""
    sample_test_cases: list[TestCase] = Field(default_factory=list)
    hidden_test_cases: list[TestCase] = Field(default_factory=list)
    reference_solution: str = ""
    reference_language: str = "python"
    supported_languages: list[str] = Field(default_factory=lambda: ["python"])
    candidate_solve_time_minutes: int = Field(default=45, ge=1, le=180)
    execution_time_limit_seconds: int = Field(default=2, ge=1, le=30)
    memory_limit_mb: int = Field(default=256, ge=64, le=2048)
    metadata_status: MetadataStatus = MetadataStatus.PENDING
    difficulty_source: DifficultySource = DifficultySource.LEGACY
    validation_report: SolutionValidationReport | None = None
    validation_status: ValidationStatus = ValidationStatus.NOT_RUN
    validation_updated_at: datetime | None = None
    reference_solutions: dict[str, ReferenceSolutionArtifact] = Field(
        default_factory=dict
    )
    answer_validation_mode: AnswerValidationMode = AnswerValidationMode.EXACT
    output_checker: str = ""
    output_checker_explanation: str = ""
    solution_approach: str = ""
    time_complexity: str = ""
    space_complexity: str = ""
    status: QuestionStatus = QuestionStatus.DRAFT
    creation_mode: QuestionCreationMode = QuestionCreationMode.MANUAL
    visibility: QuestionVisibility = QuestionVisibility.PRIVATE


class QuestionCreateRequest(QuestionBase):
    """Payload to create a question."""


class QuestionUpdateRequest(QuestionBase):
    """Payload to update a question."""


class QuestionAIDraftContext(BaseModel):
    """Current builder fields used as context for section-level AI generation."""

    title: str = ""
    problem_statement: str = ""
    difficulty: DifficultyLevel = DifficultyLevel.MEDIUM
    topics: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    category: str = ""
    constraints: str = ""
    input_format: str = ""
    input_explanation: str = ""
    output_format: str = ""
    output_explanation: str = ""
    sample_test_cases: list[TestCase] = Field(default_factory=list)
    hidden_test_cases: list[TestCase] = Field(default_factory=list)
    reference_solution: str = ""
    reference_language: str = "python"
    supported_languages: list[str] = Field(default_factory=lambda: ["python"])
    candidate_solve_time_minutes: int = Field(default=45, ge=1, le=180)
    execution_time_limit_seconds: int = Field(default=2, ge=1, le=30)
    memory_limit_mb: int = Field(default=256, ge=64, le=2048)
    metadata_status: MetadataStatus = MetadataStatus.PENDING
    difficulty_source: DifficultySource = DifficultySource.LEGACY
    validation_report: SolutionValidationReport | None = None
    validation_status: ValidationStatus = ValidationStatus.NOT_RUN
    validation_updated_at: datetime | None = None
    reference_solutions: dict[str, ReferenceSolutionArtifact] = Field(
        default_factory=dict
    )
    answer_validation_mode: AnswerValidationMode = AnswerValidationMode.EXACT
    output_checker: str = ""
    output_checker_explanation: str = ""
    solution_approach: str = ""
    time_complexity: str = ""
    space_complexity: str = ""


class QuestionRecord(QuestionBase):
    """Stored question record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    recruiter_uid: str
    created_at: datetime
    updated_at: datetime


class QuestionListResponse(BaseModel):
    """List of question records."""

    items: list[QuestionRecord]
    total: int


class QuestionBulkImportRequest(BaseModel):
    """CSV payload used to create multiple recruiter questions."""

    csv_text: str = Field(min_length=1, max_length=2_000_000)


class QuestionBulkImportRowError(BaseModel):
    """Validation errors for one CSV row."""

    row_number: int
    title: str = ""
    errors: list[str] = Field(default_factory=list)


class QuestionBulkImportResponse(BaseModel):
    """Bulk question import outcome."""

    total_rows: int
    created_count: int
    failed_count: int
    created: list[QuestionRecord] = Field(default_factory=list)
    errors: list[QuestionBulkImportRowError] = Field(default_factory=list)


class QuestionAIDraftRequest(BaseModel):
    """Prompt used to generate a recruiter-ready draft."""

    prompt: str = Field(min_length=8)
    generation_scope: Literal[
        "full",
        "basics",
        "problem",
        "problem_field",
        "constraints",
        "constraints_formats",
        "examples",
        "tests",
        "tests_solution",
        "solution",
        "other_languages",
        "recruiter_validation",
        "difficulty",
        "metadata",
    ] = "full"
    difficulty: DifficultyLevel | None = None
    reference_language: str = "python"
    target_language: str | None = Field(default=None, min_length=1, max_length=30)
    title_hint: str | None = None
    focus_tags: list[str] = Field(default_factory=list)
    current_draft: QuestionAIDraftContext | None = None
    generation_settings: QuestionGenerationSettings = Field(
        default_factory=QuestionGenerationSettings,
    )


class QuestionAIDraftResponse(BaseModel):
    """Generated draft and supporting notes."""

    draft: QuestionCreateRequest | None = None
    summary: str
    notes: list[str] = Field(default_factory=list)
    solution_validation: SolutionValidationReport | None = None
    error: str | None = None


class QuestionDraftValidationRequest(BaseModel):
    """Validate an unsaved draft against the execution service."""

    draft: QuestionAIDraftContext


class QuestionDraftValidationResponse(BaseModel):
    """Execution validation result for an unsaved draft."""

    validation_report: SolutionValidationReport


class QuestionDraftRefinementRequest(BaseModel):
    """Refine existing draft tests or source without regenerating the question."""

    draft: QuestionAIDraftContext
    generation_settings: QuestionGenerationSettings | None = None


class QuestionDraftRefinementResponse(BaseModel):
    """Refined draft plus execution evidence for the applied repair."""

    draft: QuestionCreateRequest
    validation_report: SolutionValidationReport
    summary: str
    repaired_test_case_count: int = 0
    solution_changed: bool = False


class QuestionGroupQuestionSummary(BaseModel):
    """Compact question information used inside groups."""

    id: str
    title: str
    difficulty: DifficultyLevel
    status: QuestionStatus


class QuestionGroupDifficultyBreakdown(BaseModel):
    """Question difficulty distribution for a group."""

    easy: int = 0
    medium: int = 0
    hard: int = 0


class QuestionGroupBase(BaseModel):
    """Common question group fields."""

    name: str = Field(min_length=3, max_length=180)
    description: str = ""
    question_ids: list[str] = Field(default_factory=list)
    status: QuestionGroupStatus = QuestionGroupStatus.ACTIVE


class QuestionGroupCreateRequest(QuestionGroupBase):
    """Payload to create a question group."""


class QuestionGroupUpdateRequest(QuestionGroupBase):
    """Payload to update a question group."""


class QuestionGroupRecord(QuestionGroupBase):
    """Stored question group record."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    recruiter_uid: str
    questions: list[QuestionGroupQuestionSummary] = Field(default_factory=list)
    question_count: int
    difficulty_breakdown: QuestionGroupDifficultyBreakdown
    topics: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    total_marks: int
    created_at: datetime
    updated_at: datetime


class QuestionGroupListResponse(BaseModel):
    """List of question group records."""

    items: list[QuestionGroupRecord]
    total: int
