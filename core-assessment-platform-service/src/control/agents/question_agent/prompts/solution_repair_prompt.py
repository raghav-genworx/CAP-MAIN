"""Prompt builder for reference-solution repair."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState
from .question_prompts import ADVERSARIAL_VALIDATION_ROUNDS


def build_solution_repair_prompt(
    state: QuestionGenerationState,
    *,
    source_code: str,
    sample_cases: list[dict[str, Any]],
    hidden_cases: list[dict[str, Any]],
    failing_results: list[dict[str, Any]],
    round_number: int,
    language: str,
    strict_contract_guidance: str,
    language_contract_guidance: str,
) -> tuple[str, str]:
    system_prompt = (
        "You are a reference-solution repair agent. Fix the source so it passes "
        "all accumulated tests without changing problem behavior. The "
        "`reference_solution` field must contain complete runnable source code "
        "only, never an algorithm name, pseudocode, or explanation."
    )
    user_prompt = (
        f"Round: {round_number} of {ADVERSARIAL_VALIDATION_ROUNDS}\n"
        f"Title: {state.get('title', '')}\n"
        f"Problem statement: {state.get('problem_statement', '')}\n"
        f"Constraints: {state.get('constraints', '')}\n"
        f"Input format: {state.get('input_format', '')}\n"
        f"Output format: {state.get('output_format', '')}\n"
        f"Sample tests: {sample_cases}\n"
        f"Hidden tests: {hidden_cases}\n"
        f"Failing execution results: {failing_results}\n"
        f"Current source:\n{source_code}\n"
        f"Reference language: {language}\n"
        "Return runnable source code only with no markdown fences. "
        f"{strict_contract_guidance} {language_contract_guidance} Keep the "
        "solution function-based and include the runner skeleton for stdin/stdout "
        "execution."
    )
    return system_prompt, user_prompt


__all__ = ["build_solution_repair_prompt"]
