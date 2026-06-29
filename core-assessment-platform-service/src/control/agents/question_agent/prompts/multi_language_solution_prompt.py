"""Prompt builders for multi-language solution generation."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState


def build_multi_language_solution_prompt(
    state: QuestionGenerationState,
    *,
    primary_language: str,
    target_languages: list[str],
    sample_cases: list[dict[str, Any]],
    hidden_cases: list[dict[str, Any]],
) -> tuple[str, str]:
    system_prompt = (
        "You are the multi-language solution agent. Convert a passing reference "
        "solution into equivalent complete CodeChef-style programs. Each program "
        "must read STDIN, print STDOUT, and avoid interactive prompts. Every "
        "value in `reference_solutions` must be actual source code, not an "
        "algorithm name, pseudocode, or explanation."
    )
    user_prompt = (
        f"Title: {state.get('title', '')}\n"
        f"Problem statement: {state.get('problem_statement', '')}\n"
        f"Input format: {state.get('input_format', '')}\n"
        f"Output format: {state.get('output_format', '')}\n"
        f"Constraints: {state.get('constraints', '')}\n"
        f"Sample tests: {sample_cases}\n"
        f"Hidden tests: {hidden_cases}\n"
        f"Passing {primary_language} solution:\n"
        f"{state.get('reference_solution', '')}\n"
        f"Target languages: {', '.join(target_languages)}\n"
        "Return the `reference_solutions` map with one runnable source string "
        "per target language. Keep expected behavior identical. Bad output "
        "examples: 'Kadane Algorithm', 'Use DP', or 'Approach: ...'. Good output "
        "is complete compilable/interpretable code with a solve helper and "
        "stdin/stdout runner."
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
    system_prompt = (
        "You are a focused multi-language reference-solution agent. Write one "
        "complete runnable CodeChef-style program in the target language. The "
        "`reference_solution` value must be source code only."
    )
    user_prompt = (
        f"Title: {state.get('title', '')}\n"
        f"Problem statement: {state.get('problem_statement', '')}\n"
        f"Input format: {state.get('input_format', '')}\n"
        f"Output format: {state.get('output_format', '')}\n"
        f"Constraints: {state.get('constraints', '')}\n"
        f"Sample tests: {sample_cases}\n"
        f"Hidden tests: {hidden_cases}\n"
        f"Passing {primary_language} solution:\n"
        f"{state.get('reference_solution', '')}\n"
        f"Target language: {target_language}\n"
        f"{strict_contract_guidance} {language_contract_guidance} Use the exact "
        "same accepted testcase inputs and expected outputs. Do not run an "
        "adversarial loop here; just translate the validated logic into runnable "
        "source code."
    )
    return system_prompt, user_prompt


__all__ = [
    "build_focused_language_solution_prompt",
    "build_multi_language_solution_prompt",
]
