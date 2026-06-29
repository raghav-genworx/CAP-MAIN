"""Prompt builder for testcase constraint review."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt


def build_constraint_review_prompt(
    state: QuestionGenerationState,
    *,
    bucket: str,
    constraints: str,
    test_cases: list[dict[str, Any]],
) -> tuple[str, str]:
    system_prompt = build_task_system_prompt(
        role="testcase input-contract validator",
        objective=(
            "Identify exactly which testcase inputs satisfy every supplied format "
            "rule, semantic precondition, and constraint."
        ),
        rules=(
            "Validate inputs only; do not judge expected outputs or source behavior.",
            "Indexes are one-based and refer to the supplied order.",
            "A case is valid only when all required values are present and in range.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Validate each testcase input against the problem contract.",
        context={
            "bucket": bucket,
            "problem_contract": {
                "title": state.get("title", ""),
                "problem_statement": state.get("problem_statement", ""),
                "input_format": state.get("input_format", ""),
                "constraints": constraints,
            },
            "testcases": test_cases,
        },
        requirements=(
            "Return each valid one-based index exactly once in ascending order.",
            (
                "Exclude malformed, incomplete, extra-token, out-of-range, or "
                "semantically invalid inputs."
            ),
            (
                "Add one concise invalid_notes entry per excluded index, "
                "including its index and violated rule."
            ),
            "Do not evaluate or modify expected_output.",
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_constraint_review_prompt"]
