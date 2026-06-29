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

    title: str
    problem_statement: str
    topics: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    category: str = ""
    input_format: str
    input_explanation: str = ""
    output_format: str
    output_explanation: str = ""
    constraints: str = ""
    sample_test_cases: list[TestCase] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class MetadataOutput(BaseModel):
    """Structured output for the final metadata classifier."""

    model_config = ConfigDict(extra="forbid")

    difficulty: DifficultyLevel
    topics: list[str]
    tags: list[str]
    category: str
    expected_solve_time_minutes: int
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
    constraints: str
    time_limit_minutes: int = 45
    candidate_solve_time_minutes: int = 45
    execution_time_limit_seconds: int = 2
    memory_limit_mb: int = 256
    notes: list[str] = Field(default_factory=list)


class ExampleOutput(BaseModel):
    """Structured output for the example agent."""

    model_config = ConfigDict(extra="forbid")

    sample_test_cases: list[TestCase]
    notes: list[str] = Field(default_factory=list)


class HiddenTestOutput(BaseModel):
    """Structured output for the test-case agent."""

    model_config = ConfigDict(extra="forbid")

    hidden_test_cases: list[TestCase]
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
    supported_languages: list[str]
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


class RepairDecisionOutput(BaseModel):
    """Structured decision for validation repair routing."""

    model_config = ConfigDict(extra="forbid")

    repair_target: Literal[
        "solution",
        "testcase",
        "invalid_problem",
        "execution_failure",
    ]
    rationale: str
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
    similarity_score: float
    notes: list[str] = Field(default_factory=list)


class QualityOutput(BaseModel):
    """Structured output for the quality review agent."""

    model_config = ConfigDict(extra="forbid")

    quality_score: int
    readiness_score: int
    ai_confidence_score: int
    summary: str
    notes: list[str] = Field(default_factory=list)


class QuestionGenerationState(TypedDict, total=False):
    """Mutable LangGraph state for a single question draft."""

    prompt: str
    generation_scope: str
    difficulty_hint: str
    title_hint: str
    focus_tags: list[str]
    reference_language: str
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
    "DuplicateOutput",
    "ExampleOutput",
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
