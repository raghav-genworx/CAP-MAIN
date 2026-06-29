"""Prompt builder for adversarial test generation."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState
from .question_prompts import ADVERSARIAL_TESTS_PER_ROUND, ADVERSARIAL_VALIDATION_ROUNDS


def build_adversarial_test_prompt(
    state: QuestionGenerationState,
    *,
    source_code: str,
    existing_sample_cases: list[dict[str, Any]],
    existing_hidden_cases: list[dict[str, Any]],
    round_number: int,
) -> tuple[str, str]:
    system_prompt = (
        "You are an adversarial test-case agent. Find valid edge cases that could "
        "expose bugs in the current reference solution while staying faithful to "
        "the problem statement, input format, and constraints."
    )
    user_prompt = (
        f"Round: {round_number} of {ADVERSARIAL_VALIDATION_ROUNDS}\n"
        f"Title: {state.get('title', '')}\n"
        f"Problem statement: {state.get('problem_statement', '')}\n"
        f"Constraints: {state.get('constraints', '')}\n"
        f"Input format: {state.get('input_format', '')}\n"
        f"Output format: {state.get('output_format', '')}\n"
        f"Existing sample tests: {existing_sample_cases}\n"
        f"Existing hidden tests: {existing_hidden_cases}\n"
        f"Current reference solution:\n{source_code}\n"
        "Generate only valid hidden tests with expected outputs derived from the "
        "problem statement, not from the solution. "
        f"Return at most {ADVERSARIAL_TESTS_PER_ROUND} new cases. Prefer boundary, "
        "branch, empty/minimum, maximum, and format-sensitive cases that a "
        "simplistic solution may miss."
    )
    return system_prompt, user_prompt


__all__ = ["build_adversarial_test_prompt"]
