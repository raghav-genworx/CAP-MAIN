"""Prompt builder for testcase repair."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt
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
    system_prompt = build_task_system_prompt(
        role="expected-output QC editor",
        objective=(
            "Correct only failed testcase expectations that conflict with the "
            "authoritative problem contract."
        ),
        rules=(
            "Never change testcase input text or any already-passing row.",
            "Execution actual output is diagnostic evidence, not automatic truth.",
            (
                "If the existing expectation is correct, preserve it and report "
                "that source repair is required."
            ),
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Recompute expectations only for the indexed failed testcase rows.",
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
            "preserved_testcases": {
                "sample": preserved_sample_cases,
                "hidden": preserved_hidden_cases,
            },
            "failed_indexes": {
                "sample": failing_sample_indexes,
                "hidden": failing_hidden_indexes,
            },
            "failing_execution_results": failing_results,
            "current_reference_solution": source_code,
        },
        requirements=(
            (
                "Return exactly one row per failed index in the same bucket and "
                "index order."
            ),
            "Copy each input byte-for-byte and preserve its is_sample flag.",
            (
                "Recompute expected_output from the problem contract; do not "
                "blindly copy actual_output."
            ),
            (
                "When the existing expectation is correct, return it unchanged "
                "and add a note requiring solution repair."
            ),
            "Do not return unfailed rows.",
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_testcase_repair_prompt"]
