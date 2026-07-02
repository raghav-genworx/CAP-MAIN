"""Prompt builder for the problem statement agent."""

from __future__ import annotations

from ..states.question_state import QuestionGenerationState
from .prompt_contract import (
    build_task_system_prompt,
    build_task_user_prompt,
    parse_recruiter_request,
)


def build_problem_statement_prompt(
    state: QuestionGenerationState,
    *,
    prompt: str,
    title_hint: str,
) -> tuple[str, str]:
    system_prompt = build_task_system_prompt(
        role="coding-problem specification editor",
        objective=(
            "Create a self-contained, recruiter-ready STDIN/STDOUT programming "
            "problem while preserving explicit recruiter facts."
        ),
        rules=(
            "Write candidate-visible requirements only; never create hidden behavior.",
            "Use complete-program STDIN/STDOUT semantics, not function signatures.",
            (
                "Preserve non-empty draft fields unless the requested scope "
                "requires improvement."
            ),
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Generate or refine the problem specification for the requested scope.",
        context={
            "generation_scope": state.get("generation_scope", "full"),
            "recruiter_request": parse_recruiter_request(prompt),
            "title_hint": title_hint,
            "current_draft": {
                "title": state.get("title", ""),
                "problem_statement": state.get("problem_statement", ""),
                "input_format": state.get("input_format", ""),
                "input_explanation": state.get("input_explanation", ""),
                "output_format": state.get("output_format", ""),
                "output_explanation": state.get("output_explanation", ""),
                "constraints": state.get("constraints", ""),
            },
            "focus_tags": state.get("focus_tags", []),
            "existing_question_titles": state.get("existing_question_titles", []),
        },
        requirements=(
            "Return a specific title and an unambiguous problem_statement.",
            (
                "Define every input value, output value, symbol, ordering rule, "
                "and edge behavior."
            ),
            (
                "Put the complete candidate-facing input/output descriptions "
                "directly in input_format and output_format. Leave "
                "input_explanation and output_explanation empty unless the "
                "recruiter explicitly typed separate explanation text."
            ),
            (
                "Use concise machine-checkable constraints and normalized "
                "topics, tags, and category."
            ),
            (
                "For non-full scopes, retain unrelated non-empty current_draft "
                "values and do not invent sample tests."
            ),
            (
                "Set sample_test_cases to an empty list unless valid samples "
                "already exist in context."
            ),
            "Use notes only for material assumptions or unresolved ambiguity.",
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_problem_statement_prompt"]
