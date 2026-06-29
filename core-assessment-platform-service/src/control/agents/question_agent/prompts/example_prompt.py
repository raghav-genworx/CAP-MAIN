"""Prompt builder for the sample example agent."""

from __future__ import annotations

from ..states.question_state import QuestionGenerationState


def build_example_prompt(state: QuestionGenerationState) -> tuple[str, str]:
    settings = state["generation_settings"]
    system_prompt = (
        "You are the sample example agent for a coding assessment platform. "
        "Create clear CodeChef-style sample tests that demonstrate intended "
        "behavior. Inputs must be exact STDIN strings and outputs must be exact, "
        "deterministic STDOUT strings. Every input must obey the stated input "
        "format and constraints."
    )
    user_prompt = (
        f"Title: {state.get('title', '')}\n"
        f"Recruiter description: {state['prompt']}\n"
        f"Problem statement: {state.get('problem_statement', '')}\n"
        f"Constraints: {state.get('constraints', '')}\n"
        f"Input format: {state.get('input_format', '')}\n"
        f"Output format: {state.get('output_format', '')}\n"
        f"Difficulty: {state.get('difficulty', 'medium')}\n"
        f"Required exact sample count: {settings.sample_test_case_count}\n"
        "Use the problem statement and constraints as the primary signal. "
        "Return exactly the required number of sample test cases, without hidden "
        "cases. Each sample must include an explanation that helps recruiters "
        "and candidates understand the expected behavior. Include boundary "
        "coverage only when it remains readable as a public example."
    )
    return system_prompt, user_prompt


__all__ = ["build_example_prompt"]
