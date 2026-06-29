"""Prompt builder for the constraint agent."""

from __future__ import annotations

from ..states.question_state import QuestionGenerationState
from .prompt_contract import (
    build_task_system_prompt,
    build_task_user_prompt,
    parse_recruiter_request,
)


def build_constraint_prompt(state: QuestionGenerationState) -> tuple[str, str]:
    settings = state["generation_settings"]
    system_prompt = build_task_system_prompt(
        role="programming-problem contract engineer",
        objective=(
            "Define consistent I/O formats, numeric bounds, and realistic solve "
            "and execution limits for the supplied problem."
        ),
        rules=(
            "The problem statement and explicit recruiter limits are authoritative.",
            "Every bound must name a symbol defined by the input contract.",
            "Limits must support the intended solution in every requested language.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Complete and validate the problem's I/O and constraint contract.",
        context={
            "generation_scope": state.get("generation_scope", "full"),
            "difficulty": state.get("difficulty", "medium"),
            "recruiter_request": parse_recruiter_request(state["prompt"]),
            "title": state.get("title", ""),
            "problem_statement": state.get("problem_statement", ""),
            "current_io": {
                "input_format": state.get("input_format", ""),
                "input_explanation": state.get("input_explanation", ""),
                "output_format": state.get("output_format", ""),
                "output_explanation": state.get("output_explanation", ""),
                "constraints": state.get("constraints", ""),
            },
            "requested_settings": {
                "topics": settings.topics,
                "supported_languages": settings.supported_languages,
                "candidate_solve_time_minutes": settings.candidate_solve_time_minutes,
                "execution_time_limit_seconds": settings.execution_time_limit_seconds,
                "memory_limit_mb": settings.memory_limit_mb,
            },
        },
        requirements=(
            (
                "Resolve contradictions in favor of explicit recruiter facts, "
                "then the problem statement."
            ),
            (
                "Describe exact token/line structure in input_format and exact "
                "printed value(s) in output_format."
            ),
            (
                "Explain every field and use machine-checkable inclusive bounds "
                "such as 1 <= n <= 100000."
            ),
            (
                "Keep candidate solve time in 1..180 minutes, execution time in "
                "1..30 seconds, and memory in 64..2048 MB."
            ),
            "Use notes only for a material correction or assumption.",
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_constraint_prompt"]
