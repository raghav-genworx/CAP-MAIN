"""Prompt builder for validation repair routing."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState
from .question_prompts import ADVERSARIAL_VALIDATION_ROUNDS


def build_repair_decision_prompt(
    state: QuestionGenerationState,
    *,
    source_code: str,
    sample_cases: list[dict[str, Any]],
    hidden_cases: list[dict[str, Any]],
    failing_results: list[dict[str, Any]],
    round_number: int,
) -> tuple[str, str]:
    system_prompt = (
        "You are the repair decision node for an adversarial coding-question "
        "workflow. Decide whether failed validation is most likely caused by "
        "wrong solution logic, wrong expected output, an invalid testcase, an "
        "invalid problem format, or execution infrastructure failure."
    )
    user_prompt = (
        f"Round: {round_number} of {ADVERSARIAL_VALIDATION_ROUNDS}\n"
        f"Title: {state.get('title', '')}\n"
        f"Problem statement: {state.get('problem_statement', '')}\n"
        f"Input format: {state.get('input_format', '')}\n"
        f"Output format: {state.get('output_format', '')}\n"
        f"Constraints: {state.get('constraints', '')}\n"
        f"Sample tests: {sample_cases}\n"
        f"Hidden tests: {hidden_cases}\n"
        f"Failing execution results: {failing_results}\n"
        f"Current reference solution:\n{source_code}\n"
        "Return repair_target as `testcase` when the program compiled/ran and "
        "the failure is an expected-output mismatch or invalid testcase. Prefer "
        "`testcase` in that situation because generated reference code is often "
        "more reliable than generated expected outputs. Return `solution` when "
        "there is a compile error, runtime error, missing edge-case logic, or "
        "clear source-code defect. Return `invalid_problem` if the problem is "
        "ambiguous, or `execution_failure` for infrastructure issues."
    )
    return system_prompt, user_prompt


__all__ = ["build_repair_decision_prompt"]
