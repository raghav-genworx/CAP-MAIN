"""Pure policy helpers for candidate code execution workflows."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from schemas.assessments import ExecutionCaseResult
from schemas.question_bank import TestCase

HIDDEN_CHECK_COOLDOWN_SECONDS = 5


def complete_test_cases(
    raw_cases: list[dict[str, Any]] | list[TestCase],
) -> list[TestCase]:
    """Validate test cases and retain executable expected-output pairs."""

    cases = [
        case if isinstance(case, TestCase) else TestCase.model_validate(case)
        for case in raw_cases
    ]
    return [
        case for case in cases if case.expected_output.strip()
    ]


def can_execute_final_submission(
    source_code: str,
    language: str,
    test_cases: list[TestCase],
) -> bool:
    """Return whether a final answer has everything required for execution."""

    return bool(source_code.strip() and language.strip() and test_cases)


def not_attempted_results(test_cases: list[TestCase]) -> list[ExecutionCaseResult]:
    """Build stable result evidence when the candidate submitted no answer."""

    return [
        ExecutionCaseResult(
            index=index,
            input=test_case.input,
            expected_output=test_case.expected_output,
            status="not_attempted",
            passed=False,
            message="No candidate answer was submitted for execution.",
        )
        for index, test_case in enumerate(test_cases, start=1)
    ]


def execution_failed_results(
    test_cases: list[TestCase],
) -> list[ExecutionCaseResult]:
    """Build stable evidence when the execution dependency is unavailable."""

    return [
        ExecutionCaseResult(
            index=index,
            input=test_case.input,
            expected_output=test_case.expected_output,
            status="execution_failed",
            passed=False,
            message="Execution service could not evaluate this answer.",
        )
        for index, test_case in enumerate(test_cases, start=1)
    ]


def hidden_error_type(result: ExecutionCaseResult) -> str:
    """Classify a hidden failure without exposing hidden test data."""

    if result.passed:
        return ""
    status = result.status.strip() or "Execution failed"
    normalized = status.lower()
    if "compile" in normalized:
        return "Compilation error"
    if "time" in normalized and "limit" in normalized:
        return "Time limit exceeded"
    if "memory" in normalized:
        return "Memory limit exceeded"
    if "runtime" in normalized or result.stderr.strip():
        return "Runtime error"
    if "wrong" in normalized or normalized in {"failed", "rejected"}:
        return "Wrong answer"
    return status


def hidden_check_cooldown_remaining(
    last_hidden_check_at: datetime | None,
    now: datetime,
    *,
    cooldown_seconds: int = HIDDEN_CHECK_COOLDOWN_SECONDS,
) -> int:
    """Return whole cooldown seconds remaining at the supplied instant."""

    if last_hidden_check_at is None or cooldown_seconds <= 0:
        return 0
    elapsed = int((now - last_hidden_check_at.astimezone(UTC)).total_seconds())
    return max(0, cooldown_seconds - elapsed)


def time_remaining_seconds(
    deadline_at: datetime | None,
    *,
    now: datetime | None = None,
) -> int | None:
    """Return non-negative whole seconds until a deadline."""

    if deadline_at is None:
        return None
    current = now or datetime.now(UTC)
    remaining = int((deadline_at.astimezone(UTC) - current).total_seconds())
    return max(0, remaining)
