"""State and structured-output schemas for the question agent.

=============================================================================
Two DIFFERENT kinds of models live in this file — don't confuse them:

1. `QuestionGenerationState` (bottom of file) — the ONE shared, mutable state
   that flows through the whole LangGraph. Think of it as a blackboard: every
   node reads what it needs and writes back a small patch. It is a TypedDict
   with `total=False`, meaning every key is OPTIONAL — early nodes fill in the
   basics (title, statement), later nodes add tests, solution, metadata, etc.

2. The `*Output` Pydantic models (e.g. `ProblemStatementOutput`,
   `SolutionOutput`) — strict schemas for a SINGLE LLM call. Each node asks the
   model to return JSON matching one of these (`extra="forbid"` rejects any
   stray fields), then copies the validated fields into the shared state.

So the pattern for every node is:
    LLM -> <SomethingOutput> (validated) -> copy fields into QuestionGenerationState
=============================================================================
"""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from schemas.question_bank import (
    AnswerValidationMode,
    DifficultyLevel,
    QuestionGenerationSettings,
    ReferenceSolutionArtifact,
    SolutionValidationReport,
    TestCase,
)


class ProblemStatementOutput(BaseModel):
    """Structured output for the problem statement agent."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=180)
    problem_statement: str = Field(min_length=20)
    topics: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    category: str = ""
    input_format: str = Field(min_length=3)
    input_explanation: str = ""
    output_format: str = Field(min_length=3)
    output_explanation: str = ""
    constraints: str = ""
    answer_validation_mode: AnswerValidationMode = AnswerValidationMode.EXACT
    output_checker: str = ""
    output_checker_explanation: str = ""
    sample_test_cases: list[TestCase] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ProblemStatementOnlyOutput(BaseModel):
    """Structured output when only the candidate-facing statement is requested."""

    model_config = ConfigDict(extra="forbid")

    problem_statement: str = Field(min_length=20)
    notes: list[str] = Field(default_factory=list)


class CheckerOutput(BaseModel):
    """Structured output for the output checker generator."""

    model_config = ConfigDict(extra="forbid")

    output_checker: str = Field(min_length=10)
    output_checker_explanation: str = Field(min_length=10)


class MetadataOutput(BaseModel):
    """Structured output for the final metadata classifier."""

    model_config = ConfigDict(extra="forbid")

    difficulty: DifficultyLevel
    topics: list[str] = Field(default_factory=list, max_length=0)
    tags: list[str] = Field(min_length=1, max_length=6)
    category: str = Field(min_length=2, max_length=80)
    expected_solve_time_minutes: int = Field(ge=1, le=180)
    rationale: str
    solution_approach: str = ""
    time_complexity: str = ""
    space_complexity: str = ""
    notes: list[str] = Field(default_factory=list)


class ConstraintOutput(BaseModel):
    """Structured output for the constraint agent."""

    model_config = ConfigDict(extra="forbid")

    input_format: str = ""
    input_explanation: str = ""
    output_format: str = ""
    output_explanation: str = ""
    constraints: str = Field(min_length=3)
    time_limit_minutes: int = Field(default=45, ge=1, le=180)
    candidate_solve_time_minutes: int = Field(default=45, ge=1, le=180)
    execution_time_limit_seconds: int = Field(default=2, ge=1, le=30)
    memory_limit_mb: int = Field(default=256, ge=64, le=2048)
    notes: list[str] = Field(default_factory=list)


class ExampleOutput(BaseModel):
    """Structured output for the example agent."""

    model_config = ConfigDict(extra="forbid")

    sample_test_cases: list[TestCase] = Field(min_length=1, max_length=10)
    notes: list[str] = Field(default_factory=list)


class HiddenTestOutput(BaseModel):
    """Structured output for the test-case agent."""

    model_config = ConfigDict(extra="forbid")

    hidden_test_cases: list[TestCase] = Field(min_length=1, max_length=50)
    notes: list[str] = Field(default_factory=list)


class TestCaseRepairOutput(BaseModel):
    """Structured output for replacing failed testcase rows."""

    model_config = ConfigDict(extra="forbid")

    sample_test_cases: list[TestCase] = Field(default_factory=list)
    hidden_test_cases: list[TestCase] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TestCaseConstraintReviewOutput(BaseModel):
    """Structured testcase constraint validation output."""

    model_config = ConfigDict(extra="forbid")

    valid_indexes: list[int] = Field(default_factory=list)
    invalid_notes: list[str] = Field(default_factory=list)


class ConstraintValidationScriptOutput(BaseModel):
    """Structured output for executable testcase constraint checks."""

    model_config = ConfigDict(extra="forbid")

    python_script: str = Field(
        min_length=20,
        description=(
            "Python source code defining validate_testcase(stdin: str, bucket: "
            "str) -> tuple[bool, str]. The script must not perform file IO, "
            "network IO, imports, subprocess calls, or top-level work."
        ),
    )
    notes: list[str] = Field(default_factory=list)


class SolutionOutput(BaseModel):
    """Structured output for the solution agent."""

    model_config = ConfigDict(extra="forbid")

    reference_solution: str = Field(
        description=(
            "Complete runnable source code in the requested reference language. "
            "This must not be an algorithm name, prose explanation, pseudocode, "
            "markdown, or a TODO stub."
        ),
    )
    supported_languages: list[str] = Field(min_length=1)
    solution_approach: str = Field(
        default="",
        description=(
            "Short human-readable approach explanation. Algorithm names like "
            "Kadane algorithm belong here, not in reference_solution."
        ),
    )
    time_complexity: str = ""
    space_complexity: str = ""
    reference_solutions: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Map of language to complete runnable source code for that language. "
            "Every value must be code, not an algorithm name or explanation."
        ),
    )
    notes: list[str] = Field(default_factory=list)


class FocusedLanguageSolutionOutput(BaseModel):
    """Minimal output contract for one non-primary language solution."""

    model_config = ConfigDict(extra="forbid")

    source_code: str = Field(
        min_length=1,
        description=(
            "Complete runnable source code in the single requested language. "
            "Do not include markdown fences, prose, or pseudocode."
        ),
    )


class RepairDecisionOutput(BaseModel):
    """Structured decision for validation repair routing."""

    model_config = ConfigDict(extra="forbid")

    repair_target: Literal[
        "solution",
        "testcase",
        "invalid_problem",
        "execution_failure",
    ]
    rationale: str = Field(min_length=3)
    notes: list[str] = Field(default_factory=list)


class ValidationOutput(BaseModel):
    """Structured output for the validation agent."""

    model_config = ConfigDict(extra="forbid")

    checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DuplicateOutput(BaseModel):
    """Structured output for the duplicate detection agent."""

    model_config = ConfigDict(extra="forbid")

    duplicate_warnings: list[str] = Field(default_factory=list)
    similarity_score: float = Field(ge=0, le=1)
    notes: list[str] = Field(default_factory=list)


class QualityOutput(BaseModel):
    """Structured output for the quality review agent."""

    model_config = ConfigDict(extra="forbid")

    quality_score: int = Field(ge=0, le=100)
    readiness_score: int = Field(ge=0, le=100)
    ai_confidence_score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=3, max_length=500)
    notes: list[str] = Field(default_factory=list)


class QuestionGenerationState(TypedDict, total=False):
    """Mutable LangGraph state (the "blackboard") for a single question draft.

    `total=False` => every field is optional. Fields are grouped below by which
    node first populates them, so you can trace how the draft is built up as it
    flows through the pipeline.
    """

    # ── Inputs / request context (set by `_build_initial_state`) ──────────────
    prompt: str  # the recruiter's natural-language description
    generation_scope: str  # "full" or a section like "problem"/"tests"/"solution"
    difficulty_hint: str
    title_hint: str
    focus_tags: list[str]
    reference_language: str  # primary solution language, e.g. "python"
    target_language: str  # a specific extra language to generate (optional)
    generation_settings: QuestionGenerationSettings  # counts, limits, languages
    existing_question_titles: list[str]  # used by duplicate_detection
    existing_question_tags: list[str]
    question_count: int

    # ── Written by the problem_statement node ─────────────────────────────────
    title: str
    problem_statement: str
    topics: list[str]
    tags: list[str]
    category: str
    input_format: str
    input_explanation: str
    output_format: str
    output_explanation: str
    answer_validation_mode: AnswerValidationMode | str  # exact / multiple_valid / ...
    output_checker: str  # custom checker code for non-exact answers
    output_checker_explanation: str

    # ── Written by the constraints node ───────────────────────────────────────
    constraints: str
    candidate_solve_time_minutes: int
    execution_time_limit_seconds: int
    memory_limit_mb: int

    # ── Written by the metadata node ──────────────────────────────────────────
    difficulty: str
    expected_solve_time_minutes: int
    metadata_status: str
    difficulty_source: str

    # ── Written by examples / hidden_tests / constraint_script nodes ──────────
    sample_test_cases: list[TestCase]
    hidden_test_cases: list[TestCase]
    constraint_validation_script: str  # generated Python validator for inputs
    constraint_validation_warnings: list[str]

    # ── Written by solution / validation / multi_language nodes ───────────────
    reference_solution: str  # primary solution source code
    reference_solutions: dict[str, ReferenceSolutionArtifact]  # per-language code
    supported_languages: list[str]
    validation_checks: list[str]
    validation_warnings: list[str]
    validation_status: str  # passed / failed / skipped
    solution_validation: SolutionValidationReport  # per-test execution results
    solution_approach: str
    time_complexity: str
    space_complexity: str

    # ── Written by duplicate_detection / quality_review nodes ─────────────────
    duplicate_warnings: list[str]
    quality_score: int
    readiness_score: int
    ai_confidence_score: int

    # ── Running logs appended by every node ───────────────────────────────────
    notes: list[str]  # human-readable notes surfaced to the recruiter
    execution_history: list[str]  # short per-node audit trail
    summary: str  # final one-line summary of what was generated


__all__ = [
    "ConstraintOutput",
    "ConstraintValidationScriptOutput",
    "DuplicateOutput",
    "ExampleOutput",
    "FocusedLanguageSolutionOutput",
    "HiddenTestOutput",
    "MetadataOutput",
    "ProblemStatementOutput",
    "QualityOutput",
    "QuestionGenerationState",
    "RepairDecisionOutput",
    "SolutionOutput",
    "TestCaseConstraintReviewOutput",
    "TestCaseRepairOutput",
    "ValidationOutput",
]
