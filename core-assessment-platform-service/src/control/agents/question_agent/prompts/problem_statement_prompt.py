"""Prompt builder for the problem statement agent."""

from __future__ import annotations

from ..states.question_state import QuestionGenerationState


def build_problem_statement_prompt(
    state: QuestionGenerationState,
    *,
    prompt: str,
    title_hint: str,
) -> tuple[str, str]:
    system_prompt = (
        "You are the problem statement agent for a coding assessment platform. "
        "Create recruiter-ready CodeChef-style programming questions that are "
        "clear, unambiguous, and suitable for structured interviews. Candidates "
        "write complete programs that read STDIN and print STDOUT. Do not create "
        "LeetCode-style function signatures, interactive prompts, hidden "
        "requirements, or partial implementation tasks. Preserve recruiter-entered "
        "facts and never invent constraints that conflict with existing fields."
    )
    user_prompt = (
        f"Recruiter description: {prompt}\n"
        f"Title hint: {title_hint or 'none'}\n"
        f"Existing problem statement: "
        f"{state.get('problem_statement', '') or 'none'}\n"
        f"Existing input format: {state.get('input_format', '') or 'none'}\n"
        f"Existing input explanation: "
        f"{state.get('input_explanation', '') or 'none'}\n"
        f"Existing output format: {state.get('output_format', '') or 'none'}\n"
        f"Existing output explanation: "
        f"{state.get('output_explanation', '') or 'none'}\n"
        f"Existing constraints: {state.get('constraints', '') or 'none'}\n"
        f"Focus tags: {', '.join(state.get('focus_tags', [])) or 'none'}\n"
        f"Existing question titles: "
        f"{', '.join(state.get('existing_question_titles', [])) or 'none'}\n"
        "Use the recruiter description and any existing draft fields as the "
        "source of truth. Return a polished title, complete problem statement, "
        "topics, tags, category, input format, input explanation, output format, "
        "output explanation, constraints, and sample tests when the scope asks "
        "for a full problem section. Explain what each input value represents "
        "and exactly what must be printed. Keep the statement self-contained: "
        "all symbols used in constraints or formats must be introduced in the "
        "statement or explanations."
    )
    return system_prompt, user_prompt


__all__ = ["build_problem_statement_prompt"]
