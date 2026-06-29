"""Prompt builder for the constraint agent."""

from __future__ import annotations

from ..states.question_state import QuestionGenerationState


def build_constraint_prompt(state: QuestionGenerationState) -> tuple[str, str]:
    settings = state["generation_settings"]
    system_prompt = (
        "You are the constraint agent for a coding assessment platform. "
        "Define the input format, output format, concise explanations, realistic "
        "input bounds, candidate solve time, execution time, and memory limits "
        "for CodeChef-style STDIN/STDOUT programming problems. Constraints must "
        "be specific enough to guide solution complexity and test generation, "
        "and they must not contradict the problem statement, input format, "
        "output format, or recruiter-provided limits."
    )
    user_prompt = (
        f"Difficulty: {state.get('difficulty', 'medium')}\n"
        f"Recruiter description: {state['prompt']}\n"
        f"Title: {state.get('title', '')}\n"
        f"Problem statement: {state.get('problem_statement', '')}\n"
        f"Input format: {state.get('input_format', '')}\n"
        f"Output format: {state.get('output_format', '')}\n"
        f"Topics: {', '.join(settings.topics) or 'general DSA'}\n"
        f"Supported languages: {', '.join(settings.supported_languages)}\n"
        "Use the problem statement as the primary signal. Return input format, "
        "input explanation, output format, output explanation, concise "
        "constraints, candidate solve time, execution time limit in seconds, "
        "and memory limit. Prefer machine-checkable numeric bounds such as "
        "`1 <= n <= 10^5` where possible, because generated tests are filtered "
        "against these bounds before validation."
    )
    return system_prompt, user_prompt


__all__ = ["build_constraint_prompt"]
