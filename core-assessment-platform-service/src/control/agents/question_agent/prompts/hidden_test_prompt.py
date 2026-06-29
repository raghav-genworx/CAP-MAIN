"""Prompt builder for the hidden test-case agent."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState


def build_hidden_test_prompt(
    state: QuestionGenerationState,
    *,
    sample_cases: list[dict[str, Any]],
) -> tuple[str, str]:
    settings = state["generation_settings"]
    system_prompt = (
        "You are the hidden test-case agent for a coding assessment platform. "
        "Generate hidden, edge, and stress cases that validate correctness for "
        "complete STDIN/STDOUT programs. Test inputs must obey the stated input "
        "format and constraints, and expected outputs must be deterministic."
    )
    user_prompt = (
        f"Title: {state.get('title', '')}\n"
        f"Recruiter description: {state['prompt']}\n"
        f"Problem statement: {state.get('problem_statement', '')}\n"
        f"Constraints: {state.get('constraints', '')}\n"
        f"Input format: {state.get('input_format', '')}\n"
        f"Output format: {state.get('output_format', '')}\n"
        f"Sample tests: {sample_cases}\n"
        f"Difficulty: {state.get('difficulty', 'medium')}\n"
        f"Required exact hidden count: {settings.hidden_test_case_count}\n"
        f"Requested edge count: {settings.edge_case_count}\n"
        f"Requested stress count: {settings.stress_test_count}\n"
        "Use the problem statement, constraints, and sample tests as the primary "
        "signal. Return exactly the required hidden count total. Edge and stress "
        "cases must be part of that total, not extra rows. Expected outputs must "
        "be derived from the problem statement, not from the reference solution."
    )
    return system_prompt, user_prompt


__all__ = ["build_hidden_test_prompt"]
