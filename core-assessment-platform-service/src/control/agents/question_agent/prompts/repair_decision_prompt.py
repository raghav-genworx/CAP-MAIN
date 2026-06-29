"""Prompt builder for validation repair routing."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt
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
    system_prompt = build_task_system_prompt(
        role="validation failure triage specialist",
        objective=(
            "Route a failed QC run to the single most evidence-supported repair "
            "target without changing the intended problem."
        ),
        rules=(
            (
                "Authority order is problem contract, valid testcase semantics, "
                "then execution evidence."
            ),
            "Do not assume actual output is correct merely because the program ran.",
            "Use execution_failure only for compiler/runner infrastructure evidence.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Classify the root cause of the failed validation run.",
        context={
            "qc_round": {
                "current": round_number,
                "maximum": ADVERSARIAL_VALIDATION_ROUNDS,
            },
            "problem_contract": {
                "title": state.get("title", ""),
                "problem_statement": state.get("problem_statement", ""),
                "input_format": state.get("input_format", ""),
                "output_format": state.get("output_format", ""),
                "constraints": state.get("constraints", ""),
            },
            "testcases": {"sample": sample_cases, "hidden": hidden_cases},
            "failing_execution_results": failing_results,
            "current_reference_solution": source_code,
        },
        requirements=(
            (
                "Choose solution for compile/runtime defects or source logic "
                "that conflicts with the contract."
            ),
            (
                "Choose testcase only when an input is invalid or "
                "expected_output conflicts with the contract."
            ),
            (
                "Choose invalid_problem only when the candidate-visible contract "
                "cannot determine one correct behavior."
            ),
            (
                "Choose execution_failure only for runner, compiler service, "
                "timeout-service, or unavailable-tool evidence."
            ),
            "Give a concise evidence-based rationale and only material notes.",
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_repair_decision_prompt"]
