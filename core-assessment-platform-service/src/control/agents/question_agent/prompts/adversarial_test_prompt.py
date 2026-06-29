"""Prompt builder for adversarial test generation."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt
from .question_prompts import ADVERSARIAL_TESTS_PER_ROUND, ADVERSARIAL_VALIDATION_ROUNDS


def build_adversarial_test_prompt(
    state: QuestionGenerationState,
    *,
    source_code: str,
    existing_sample_cases: list[dict[str, Any]],
    existing_hidden_cases: list[dict[str, Any]],
    round_number: int,
) -> tuple[str, str]:
    system_prompt = build_task_system_prompt(
        role="adversarial testcase challenger",
        objective=(
            "Find new contract-valid inputs that expose likely defects in the "
            "current solution."
        ),
        rules=(
            (
                "Derive expected outputs from the problem contract, never from "
                "current source behavior."
            ),
            "Return no duplicate input from the supplied sample or hidden suites.",
            "Prefer high-value boundaries and semantic branches over random cases.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Generate a small adversarial hidden-test challenge for this QC round.",
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
            "existing_testcases": {
                "sample": existing_sample_cases,
                "hidden": existing_hidden_cases,
            },
            "current_reference_solution": source_code,
            "maximum_new_cases": ADVERSARIAL_TESTS_PER_ROUND,
        },
        requirements=(
            "Return 0..maximum_new_cases hidden_test_cases and set is_sample=false.",
            (
                "Target a concrete likely weakness in the source while keeping "
                "every input contract-valid."
            ),
            "Recompute exact expected STDOUT independently from the problem statement.",
            "Use an empty list when no distinct high-value valid case exists.",
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_adversarial_test_prompt"]
