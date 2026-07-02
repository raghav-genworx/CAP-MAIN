"""Prompt builder for replacing constraint-invalid test cases."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt


def build_constraint_replacement_prompt(
    state: QuestionGenerationState,
    *,
    invalid_sample_cases: list[dict[str, Any]],
    invalid_hidden_cases: list[dict[str, Any]],
    valid_sample_cases: list[dict[str, Any]],
    valid_hidden_cases: list[dict[str, Any]],
    script_rejections: list[dict[str, Any]],
    attempt: int,
) -> tuple[str, str]:
    system_prompt = build_task_system_prompt(
        role="constraint-valid testcase replacement agent",
        objective=(
            "Replace only testcase rows rejected by the constraint validation "
            "script with new rows that satisfy the problem contract."
        ),
        rules=(
            "Do not modify already-valid rows.",
            "Replacement inputs must satisfy the problem statement, input "
            "format, and constraints.",
            "Expected outputs must be recomputed from the problem contract, "
            "not from a solution.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Generate replacement rows for constraint-invalid testcases.",
        context={
            "attempt": attempt,
            "problem_contract": {
                "title": state.get("title", ""),
                "problem_statement": state.get("problem_statement", ""),
                "input_format": state.get("input_format", ""),
                "input_explanation": state.get("input_explanation", ""),
                "output_format": state.get("output_format", ""),
                "output_explanation": state.get("output_explanation", ""),
                "constraints": state.get("constraints", ""),
            },
            "already_valid_testcases": {
                "sample": valid_sample_cases,
                "hidden": valid_hidden_cases,
            },
            "invalid_testcases_to_replace": {
                "sample": invalid_sample_cases,
                "hidden": invalid_hidden_cases,
            },
            "script_rejections": script_rejections,
        },
        requirements=(
            "Return exactly one replacement sample row per invalid sample row.",
            "Return exactly one replacement hidden row per invalid hidden row.",
            "Set is_sample=true for sample replacements and false for "
            "hidden replacements.",
            "Do not duplicate any input already present in already_valid_testcases.",
            "Use notes only for a material ambiguity or fallback assumption.",
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_constraint_replacement_prompt"]
