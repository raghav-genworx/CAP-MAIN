"""Prompt builder for the primary reference-solution agent."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt


def build_solution_prompt(
    state: QuestionGenerationState,
    *,
    reference_language: str,
    sample_cases: list[dict[str, Any]],
    hidden_cases: list[dict[str, Any]],
    strict_contract_guidance: str,
    language_contract_guidance: str,
) -> tuple[str, str]:
    system_prompt = build_task_system_prompt(
        role="reference-solution engineer",
        objective=(
            "Produce a correct, efficient, complete program for the supplied "
            "problem in the requested primary language."
        ),
        rules=(
            "Solve the full constrained domain, not only the supplied tests.",
            (
                "Source code must be deterministic and directly executable "
                "against STDIN/STDOUT."
            ),
            "Complexity claims must match the implementation.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task=(
            "Generate the primary reference solution and its exact complexity metadata."
        ),
        context={
            "problem_contract": {
                "title": state.get("title", ""),
                "problem_statement": state.get("problem_statement", ""),
                "input_format": state.get("input_format", ""),
                "output_format": state.get("output_format", ""),
                "constraints": state.get("constraints", ""),
            },
            "testcases": {"sample": sample_cases, "hidden": hidden_cases},
            "difficulty": state.get("difficulty", "medium"),
            "reference_language": reference_language,
            "requested_languages": state["generation_settings"].supported_languages,
        },
        requirements=(
            strict_contract_guidance,
            language_contract_guidance,
            (
                "Set reference_solution to source code only, without markdown "
                "fences or prose."
            ),
            (
                "Set reference_solutions to an empty object; other languages are "
                "generated separately after validation."
            ),
            (
                "Set supported_languages to the requested languages only, "
                "normalized without duplicates."
            ),
            (
                "Provide a concise general solution_approach and accurate Big-O "
                "time_complexity and space_complexity."
            ),
            "Use notes only for a material assumption.",
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_solution_prompt"]
