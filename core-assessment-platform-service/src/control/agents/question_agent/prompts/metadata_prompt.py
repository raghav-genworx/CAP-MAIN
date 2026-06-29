"""Prompt builder for the metadata classifier agent."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState


def build_metadata_prompt(
    state: QuestionGenerationState,
    *,
    sample_cases: list[dict[str, Any]],
    hidden_cases: list[dict[str, Any]],
    validation_summary: str,
) -> tuple[str, str]:
    system_prompt = (
        "You are the final metadata classifier for a coding assessment platform. "
        "Classify only after reviewing the final problem, test coverage, "
        "execution validation, and reference solution. Keep labels concise, "
        "consistent, and useful for recruiter filtering."
    )
    user_prompt = (
        f"Title: {state.get('title', '')}\n"
        f"Problem statement: {state.get('problem_statement', '')}\n"
        f"Recruiter description: {state['prompt']}\n"
        f"Input format: {state.get('input_format', '')}\n"
        f"Input explanation: {state.get('input_explanation', '')}\n"
        f"Output format: {state.get('output_format', '')}\n"
        f"Output explanation: {state.get('output_explanation', '')}\n"
        f"Constraints: {state.get('constraints', '')}\n"
        f"Sample tests: {sample_cases}\n"
        f"Hidden tests: {hidden_cases}\n"
        f"Reference solution: {state.get('reference_solution', '')}\n"
        f"Execution validation: {validation_summary}\n"
        "Return difficulty, 3-6 topics, 3-6 tags, one category, expected solve "
        "time, solution approach, time complexity, space complexity, and a short "
        "rationale grounded in the final draft."
    )
    return system_prompt, user_prompt


__all__ = ["build_metadata_prompt"]
