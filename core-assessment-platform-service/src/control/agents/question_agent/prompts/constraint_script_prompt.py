"""Prompt builder for executable testcase constraint validation scripts."""

from __future__ import annotations

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt


def build_constraint_script_prompt(state: QuestionGenerationState) -> tuple[str, str]:
    system_prompt = build_task_system_prompt(
        role="testcase constraint-script engineer",
        objective=(
            "Write a small Python validator that checks whether raw testcase "
            "inputs satisfy the supplied problem contract."
        ),
        rules=(
            "Define exactly validate_testcase(stdin: str, bucket: str) -> "
            "tuple[bool, str].",
            "Return True only when the input format, semantic requirements, "
            "and constraints all pass.",
            "Do not import modules, read files, access the network, spawn "
            "processes, print, or do top-level work.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task=(
            "Generate the Python constraint validator used before solution generation."
        ),
        context={
            "problem_contract": {
                "title": state.get("title", ""),
                "problem_statement": state.get("problem_statement", ""),
                "input_format": state.get("input_format", ""),
                "input_explanation": state.get("input_explanation", ""),
                "output_format": state.get("output_format", ""),
                "constraints": state.get("constraints", ""),
            },
        },
        requirements=(
            "Set python_script to source code only; no markdown fences.",
            "The script must be deterministic and must not inspect expected_output.",
            "The function must parse stdin exactly as the candidate program "
            "receives it.",
            "Return (False, concise_reason) for malformed input, missing "
            "values, extra tokens, out-of-range values, or violated semantic "
            "constraints.",
            "Return (True, 'ok') only when every stated input constraint passes.",
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_constraint_script_prompt"]
