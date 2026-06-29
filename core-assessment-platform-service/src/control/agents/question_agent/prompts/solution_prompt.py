"""Prompt builder for the primary reference-solution agent."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState


def build_solution_prompt(
    state: QuestionGenerationState,
    *,
    reference_language: str,
    sample_cases: list[dict[str, Any]],
    hidden_cases: list[dict[str, Any]],
    strict_contract_guidance: str,
    language_contract_guidance: str,
) -> tuple[str, str]:
    system_prompt = (
        "You are the reference-solution agent for a coding assessment platform. "
        "Produce a clean implementation in the requested language. It must be a "
        "complete runnable CodeChef-style program that reads STDIN and prints "
        "STDOUT. It must not print prompts such as 'Enter number:'. The "
        "`reference_solution` field must contain source code only, never an "
        "algorithm name, pseudocode, explanation, or labels like 'Kadane "
        "Algorithm'."
    )
    user_prompt = (
        f"Title: {state.get('title', '')}\n"
        f"Recruiter description: {state['prompt']}\n"
        f"Problem statement: {state.get('problem_statement', '')}\n"
        f"Constraints: {state.get('constraints', '')}\n"
        f"Input format: {state.get('input_format', '')}\n"
        f"Output format: {state.get('output_format', '')}\n"
        f"Sample tests: {sample_cases}\n"
        f"Hidden tests: {hidden_cases}\n"
        f"Difficulty: {state.get('difficulty', 'medium')}\n"
        f"Reference language: {reference_language}\n"
        f"Supported languages requested: "
        f"{', '.join(state['generation_settings'].supported_languages)}\n"
        "Use the problem statement, constraints, and test cases as the primary "
        "signal. Return runnable source code only with no markdown fences. "
        f"{strict_contract_guidance} {language_contract_guidance} Include any "
        "helper function and a runner in the same source so it can be executed "
        "directly against stdin/stdout test cases. Return solution approach, "
        "time complexity, and space complexity."
    )
    return system_prompt, user_prompt


__all__ = ["build_solution_prompt"]
