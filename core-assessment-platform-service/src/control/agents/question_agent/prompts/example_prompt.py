"""Prompt builder for the sample example agent."""

from __future__ import annotations

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt


def build_example_prompt(state: QuestionGenerationState) -> tuple[str, str]:
    settings = state["generation_settings"]
    system_prompt = build_task_system_prompt(
        role="public testcase designer",
        objective=(
            "Create exact, correct sample cases that teach the supplied problem "
            "without duplicating behavior."
        ),
        rules=(
            "Derive outputs independently from the problem contract.",
            "Each sample input must satisfy every format rule and constraint.",
            "Sample explanations must describe why the output follows from the input.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Generate the exact requested number of public sample testcases.",
        context={
            "problem_contract": {
                "title": state.get("title", ""),
                "problem_statement": state.get("problem_statement", ""),
                "input_format": state.get("input_format", ""),
                "output_format": state.get("output_format", ""),
                "constraints": state.get("constraints", ""),
            },
            "difficulty": state.get("difficulty", "medium"),
            "required_sample_count": settings.sample_test_case_count,
        },
        requirements=(
            (
                "Return exactly required_sample_count rows and set is_sample=true "
                "for every row."
            ),
            (
                "Use raw STDIN and STDOUT strings with required newlines "
                "represented inside the JSON string."
            ),
            (
                "Cover distinct normal or readable boundary behavior; do not "
                "duplicate inputs."
            ),
            (
                "Recompute every expected_output and include a concise "
                "explanation for each row."
            ),
            "Use notes only for a material ambiguity in the problem contract.",
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_example_prompt"]
