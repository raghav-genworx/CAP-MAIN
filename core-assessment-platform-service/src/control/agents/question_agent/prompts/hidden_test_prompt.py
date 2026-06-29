"""Prompt builder for the hidden test-case agent."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt


def build_hidden_test_prompt(
    state: QuestionGenerationState,
    *,
    sample_cases: list[dict[str, Any]],
) -> tuple[str, str]:
    settings = state["generation_settings"]
    system_prompt = build_task_system_prompt(
        role="hidden testcase and edge-case designer",
        objective=(
            "Create valid hidden cases that distinguish correct general solutions "
            "from common wrong implementations."
        ),
        rules=(
            "Derive expected outputs independently from the problem contract.",
            "Never duplicate a public sample or another hidden input.",
            "Stress cases must remain representable as exact complete input strings.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Generate the exact requested hidden testcase suite.",
        context={
            "problem_contract": {
                "title": state.get("title", ""),
                "problem_statement": state.get("problem_statement", ""),
                "input_format": state.get("input_format", ""),
                "output_format": state.get("output_format", ""),
                "constraints": state.get("constraints", ""),
            },
            "difficulty": state.get("difficulty", "medium"),
            "public_samples": sample_cases,
            "counts": {
                "hidden_total": settings.hidden_test_case_count,
                "edge_within_total": settings.edge_case_count,
                "stress_within_total": settings.stress_test_count,
            },
        },
        requirements=(
            (
                "Return exactly counts.hidden_total rows and set is_sample=false "
                "for every row."
            ),
            (
                "Include edge and stress rows within the total; do not add them "
                "beyond the total."
            ),
            (
                "Prioritize minimum/maximum bounds, branch boundaries, "
                "duplicates, signs, ordering, and overflow when applicable."
            ),
            "Use only contract-valid inputs and exact deterministic STDOUT outputs.",
            (
                "Keep hidden explanations short and do not reveal hidden cases "
                "through notes."
            ),
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_hidden_test_prompt"]
