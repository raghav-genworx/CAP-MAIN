"""Prompt builder for testcase constraint review."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState


def build_constraint_review_prompt(
    state: QuestionGenerationState,
    *,
    bucket: str,
    constraints: str,
    test_cases: list[dict[str, Any]],
) -> tuple[str, str]:
    system_prompt = (
        "You are a strict testcase constraint validator. Mark a testcase valid "
        "only when its input obeys the stated constraints, input format, and "
        "problem statement. Do not judge whether the expected output is produced "
        "by the reference solution here."
    )
    user_prompt = (
        f"Bucket: {bucket}\n"
        f"Title: {state.get('title', '')}\n"
        f"Problem statement: {state.get('problem_statement', '')}\n"
        f"Input format: {state.get('input_format', '')}\n"
        f"Constraints: {constraints}\n"
        "Testcases are 1-indexed. Return valid_indexes only for cases whose "
        "inputs satisfy every constraint.\n"
        f"Testcases: {test_cases}"
    )
    return system_prompt, user_prompt


__all__ = ["build_constraint_review_prompt"]
