"""Prompt builder for testcase repair."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState
from .question_prompts import ADVERSARIAL_VALIDATION_ROUNDS


def build_testcase_repair_prompt(
    state: QuestionGenerationState,
    *,
    source_code: str,
    preserved_sample_cases: list[dict[str, Any]],
    preserved_hidden_cases: list[dict[str, Any]],
    failing_sample_indexes: list[int],
    failing_hidden_indexes: list[int],
    failing_results: list[dict[str, Any]],
    round_number: int,
) -> tuple[str, str]:
    system_prompt = (
        "You are a testcase repair agent. Replace only failed sample or hidden "
        "testcase rows when their input is invalid or their expected output is "
        "wrong. Preserve the intended problem behavior and do not change "
        "already-passing rows."
    )
    user_prompt = (
        f"Round: {round_number} of {ADVERSARIAL_VALIDATION_ROUNDS}\n"
        f"Title: {state.get('title', '')}\n"
        f"Problem statement: {state.get('problem_statement', '')}\n"
        f"Constraints: {state.get('constraints', '')}\n"
        f"Input format: {state.get('input_format', '')}\n"
        f"Output format: {state.get('output_format', '')}\n"
        f"Preserved sample tests: {preserved_sample_cases}\n"
        f"Preserved hidden tests: {preserved_hidden_cases}\n"
        f"Failed sample indexes: {failing_sample_indexes}\n"
        f"Failed hidden indexes: {failing_hidden_indexes}\n"
        f"Failing execution results: {failing_results}\n"
        f"Reference solution that should pass valid tests:\n{source_code}\n"
        "Return replacement rows only for failed indexes. Put sample replacements "
        "in `sample_test_cases` and hidden replacements in `hidden_test_cases`. "
        "The expected outputs must be the correct deterministic STDOUT for the "
        "testcase input. Do not duplicate preserved tests."
    )
    return system_prompt, user_prompt


__all__ = ["build_testcase_repair_prompt"]
