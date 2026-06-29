"""Schemas for code execution requests and responses."""

from typing import Any

from pydantic import BaseModel, Field, model_validator


class ExecutionRequest(BaseModel):
    """Code execution payload accepted by the service."""

    source_code: str = Field(min_length=1, max_length=200_000)
    language_id: int | None = Field(default=None, ge=1)
    language: str | None = Field(default=None, min_length=1, max_length=50)
    stdin: str | None = Field(default=None, max_length=100_000)
    expected_output: str | None = Field(default=None, max_length=100_000)
    compiler_options: str | None = Field(default=None, max_length=512)
    command_line_arguments: str | None = Field(default=None, max_length=512)
    cpu_time_limit: float | None = Field(default=None, gt=0, le=15)
    memory_limit: int | None = Field(default=None, ge=1024, le=512_000)

    @model_validator(mode="after")
    def require_language(self) -> "ExecutionRequest":
        """Require either a Judge0 language ID or a supported language alias."""

        if self.language_id is None and self.language is None:
            raise ValueError("Either language_id or language is required.")
        return self


class Judge0Status(BaseModel):
    """Judge0 submission status."""

    id: int
    description: str


class ExecutionResponse(BaseModel):
    """Normalized result returned to API consumers."""

    token: str
    status: Judge0Status
    stdout: str | None = None
    stderr: str | None = None
    compile_output: str | None = None
    message: str | None = None
    time: str | None = None
    wall_time: str | None = None
    memory: int | None = None
    exit_code: int | None = None
    exit_signal: int | None = None


class LanguageResponse(BaseModel):
    """Supported language metadata returned by Judge0."""

    id: int
    name: str


class BatchTestCase(BaseModel):
    """One batch execution test case."""

    input: str
    expected_output: str


class BatchExecutionRequest(BaseModel):
    """Execute one source against multiple test cases."""

    source_code: str = Field(min_length=1, max_length=200_000)
    language_id: int | None = Field(default=None, ge=1)
    language: str | None = Field(default=None, min_length=1, max_length=50)
    run_type: str = Field(default="sample_run", min_length=1, max_length=40)
    test_cases: list[BatchTestCase] = Field(
        default_factory=list, min_length=1, max_length=200
    )
    cpu_time_limit: float | None = Field(default=None, gt=0, le=15)
    memory_limit: int | None = Field(default=None, ge=1024, le=512_000)

    @model_validator(mode="after")
    def require_language(self) -> "BatchExecutionRequest":
        if self.language_id is None and self.language is None:
            raise ValueError("Either language_id or language is required.")
        return self


class BatchExecutionCaseResult(BaseModel):
    """Normalized per-case batch result."""

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


class BatchExecutionResponse(BaseModel):
    """Aggregated batch execution result."""

    run_type: str
    passed_count: int
    total_count: int
    results: list[BatchExecutionCaseResult] = Field(default_factory=list)


class Judge0SubmissionResult(BaseModel):
    """Internal model for Judge0 submission responses."""

    token: str
    status: Judge0Status | None = None
    stdout: str | None = None
    stderr: str | None = None
    compile_output: str | None = None
    message: str | None = None
    time: str | None = None
    wall_time: str | None = None
    memory: int | None = None
    exit_code: int | None = None
    exit_signal: int | None = None

    model_config = {"extra": "ignore"}


Judge0Payload = dict[str, Any]
