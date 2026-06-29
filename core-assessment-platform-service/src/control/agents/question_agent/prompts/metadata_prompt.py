"""Prompt builder for the metadata classifier agent."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt


def build_metadata_prompt(
    state: QuestionGenerationState,
    *,
    sample_cases: list[dict[str, Any]],
    hidden_cases: list[dict[str, Any]],
    validation_summary: str,
) -> tuple[str, str]:
    system_prompt = build_task_system_prompt(
        role="coding-question metadata classifier",
        objective=(
            "Classify the final question using concise normalized metadata grounded "
            "only in its actual solution requirements."
        ),
        rules=(
            (
                "Infer difficulty from required reasoning, implementation risk, "
                "and constraints."
            ),
            (
                "Use recruiter-searchable topic and tag labels without synonyms "
                "or duplicates."
            ),
            "Complexity and approach must describe the supplied reference solution.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Classify the finalized and execution-checked question.",
        context={
            "problem_contract": {
                "title": state.get("title", ""),
                "problem_statement": state.get("problem_statement", ""),
                "input_format": state.get("input_format", ""),
                "input_explanation": state.get("input_explanation", ""),
                "output_format": state.get("output_format", ""),
                "output_explanation": state.get("output_explanation", ""),
                "constraints": state.get("constraints", ""),
            },
            "testcases": {"sample": sample_cases, "hidden": hidden_cases},
            "reference_solution": state.get("reference_solution", ""),
            "execution_validation_summary": validation_summary,
        },
        requirements=(
            (
                "Return difficulty as easy, medium, or hard based on the full "
                "constrained problem."
            ),
            (
                "Return 3..6 normalized topics, 3..6 specific tags, and one broad "
                "category."
            ),
            "Set expected_solve_time_minutes to a realistic value in 1..180.",
            (
                "Provide one concise rationale and exact solution approach, time "
                "complexity, and space complexity."
            ),
            (
                "Use notes only for validation limitations that affect "
                "classification confidence."
            ),
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_metadata_prompt"]
