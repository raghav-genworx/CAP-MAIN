"""State and structured-output schemas for the question agent."""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field

from schemas.question_bank import (
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
    sample_test_cases: list[TestCase] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class MetadataOutput(BaseModel):
    """Structured output for the final metadata classifier."""

    model_config = ConfigDict(extra="forbid")

    difficulty: DifficultyLevel
    topics: list[str] = Field(min_length=3, max_length=6)
    tags: list[str] = Field(min_length=3, max_length=6)
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

    hidden_test_cases: list[TestCase] = Field(max_length=50)
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
    """Mutable LangGraph state for a single question draft."""

    prompt: str
    generation_scope: str
    difficulty_hint: str
    title_hint: str
    focus_tags: list[str]
    reference_language: str
    target_language: str
    generation_settings: QuestionGenerationSettings
    existing_question_titles: list[str]
    existing_question_tags: list[str]
    question_count: int
    title: str
    problem_statement: str
    topics: list[str]
    tags: list[str]
    category: str
    constraints: str
    input_format: str
    input_explanation: str
    output_format: str
    output_explanation: str
    difficulty: str
    expected_solve_time_minutes: int
    candidate_solve_time_minutes: int
    execution_time_limit_seconds: int
    memory_limit_mb: int
    metadata_status: str
    difficulty_source: str
    sample_test_cases: list[TestCase]
    hidden_test_cases: list[TestCase]
    constraint_validation_script: str
    constraint_validation_warnings: list[str]
    reference_solution: str
    reference_solutions: dict[str, ReferenceSolutionArtifact]
    supported_languages: list[str]
    validation_checks: list[str]
    validation_warnings: list[str]
    validation_status: str
    solution_validation: SolutionValidationReport
    solution_approach: str
    time_complexity: str
    space_complexity: str
    duplicate_warnings: list[str]
    quality_score: int
    readiness_score: int
    ai_confidence_score: int
    notes: list[str]
    execution_history: list[str]
    summary: str


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
