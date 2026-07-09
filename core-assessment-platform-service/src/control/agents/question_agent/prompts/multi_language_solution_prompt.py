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
            (
                "Each translated solution must remain optimized for the declared "
                "complexity and must not downgrade to a brute-force approach."
            ),
            "Keep complexity fields consistent with the translated implementation.",
        ),
    )
    return system_prompt, user_prompt


def build_focused_language_solution_prompt(
    state: QuestionGenerationState,
    *,
    target_language: str,
    sample_cases: list[dict[str, Any]],
    hidden_cases: list[dict[str, Any]],
    strict_contract_guidance: str,
    language_contract_guidance: str,
) -> tuple[str, str]:
    system_prompt = build_task_system_prompt(
        role=f"expert {target_language} competitive-programming engineer",
        objective=(
            f"Write one correct, efficient, complete {target_language} program "
            "that solves the supplied problem contract."
        ),
        rules=(
            f"Generate {target_language} source code only.",
            "Preserve integer semantics and exact output formatting.",
            ("Use idiomatic input parsing that handles the full input contract."),
            (
                "Derive the solution directly from the problem, constraints, "
                "samples, and hidden validation cases."
            ),
            "Keep the optimized intended algorithm; do not use brute force.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task=f"Generate the complete runnable solution in {target_language} only.",
        context={
            "target_language": target_language,
            "title": state.get("title", ""),
            "problem_statement": state.get("problem_statement", ""),
            "constraints": state.get("constraints", ""),
            "input_format": state.get("input_format", ""),
            "output_format": state.get("output_format", ""),
            "sample_test_cases": sample_cases,
            "hidden_test_cases": hidden_cases,
            "answer_validation": {
                "mode": state.get("answer_validation_mode", "exact"),
                "explanation": state.get("output_checker_explanation", ""),
            },
            "recruiter_instruction": state.get("prompt", ""),
        },
        requirements=(
            strict_contract_guidance,
            language_contract_guidance,
            "Set source_code to the complete target-language program only.",
            (
                "The program must satisfy every sample and the full constrained "
                "input domain, including edge cases."
            ),
            (
                "If answer_validation.mode is multiple_valid or constructive, "
                "the program may print any valid answer accepted by the checker "
                "rather than matching the exemplar output byte-for-byte."
            ),
            "Do not return any fields other than source_code.",
            f"Do not generate any language other than {target_language}.",
        ),
    )
    return system_prompt, user_prompt


__all__ = [
    "build_focused_language_solution_prompt",
    "build_multi_language_solution_prompt",
]
