"""Prompt builders for multi-language solution generation."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt


def build_multi_language_solution_prompt(
    state: QuestionGenerationState,
    *,
    primary_language: str,
    target_languages: list[str],
    sample_cases: list[dict[str, Any]],
    hidden_cases: list[dict[str, Any]],
) -> tuple[str, str]:
    system_prompt = build_task_system_prompt(
        role="multi-language reference-solution engineer",
        objective=(
            "Translate validated logic into behaviorally equivalent, complete "
            "STDIN/STDOUT programs for the requested target languages."
        ),
        rules=(
            (
                "Preserve integer semantics, overflow safety, indexing, and "
                "output formatting."
            ),
            "Each source value must be directly compilable or interpretable.",
            "Generate only the requested target languages.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Generate equivalent runnable programs for every target language.",
        context={
            "problem_contract": {
                "title": state.get("title", ""),
                "problem_statement": state.get("problem_statement", ""),
                "input_format": state.get("input_format", ""),
                "output_format": state.get("output_format", ""),
                "constraints": state.get("constraints", ""),
            },
            "testcases": {"sample": sample_cases, "hidden": hidden_cases},
            "validated_primary": {
                "language": primary_language,
                "source_code": state.get("reference_solution", ""),
            },
            "target_languages": target_languages,
        },
        requirements=(
            (
                "Set reference_solutions to exactly one complete source string "
                "per target language."
            ),
            (
                "Set reference_solution to an empty string because this is a "
                "batch translation response."
            ),
            (
                "Set supported_languages to target_languages in the same order "
                "without duplicates."
            ),
            (
                "Preserve the validated algorithm and exact STDOUT behavior "
                "across languages."
            ),
            "Keep complexity fields consistent with the translated implementation.",
        ),
    )
    return system_prompt, user_prompt


def build_focused_language_solution_prompt(
    state: QuestionGenerationState,
    *,
    target_language: str,
    primary_language: str,
    sample_cases: list[dict[str, Any]],
    hidden_cases: list[dict[str, Any]],
    strict_contract_guidance: str,
    language_contract_guidance: str,
) -> tuple[str, str]:
    system_prompt = build_task_system_prompt(
        role="single-language reference-solution translator",
        objective=(
            "Translate validated solution logic into one correct, efficient, "
            "complete program in the target language."
        ),
        rules=(
            "Preserve behavior, integer semantics, and exact output formatting.",
            (
                "Use idiomatic target-language input parsing that handles the "
                "full input contract."
            ),
            "Do not change the algorithm unless required for equivalent correctness.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Translate the validated primary solution into the target language.",
        context={
            "problem_contract": {
                "title": state.get("title", ""),
                "problem_statement": state.get("problem_statement", ""),
                "input_format": state.get("input_format", ""),
                "output_format": state.get("output_format", ""),
                "constraints": state.get("constraints", ""),
            },
            "testcases": {"sample": sample_cases, "hidden": hidden_cases},
            "validated_primary": {
                "language": primary_language,
                "source_code": state.get("reference_solution", ""),
            },
            "target_language": target_language,
        },
        requirements=(
            strict_contract_guidance,
            language_contract_guidance,
            "Set reference_solution to target-language source code only.",
            (
                "Set supported_languages to only target_language and "
                "reference_solutions to an empty object."
            ),
            (
                "Preserve exact accepted behavior for all supplied tests and the "
                "full constrained domain."
            ),
            "Keep solution_approach and complexity fields consistent with the source.",
        ),
    )
    return system_prompt, user_prompt


__all__ = [
    "build_focused_language_solution_prompt",
    "build_multi_language_solution_prompt",
]
