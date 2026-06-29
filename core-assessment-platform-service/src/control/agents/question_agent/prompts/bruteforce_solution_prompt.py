"""Prompt builder for correctness-first oracle solution generation."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt


def build_bruteforce_solution_prompt(
    state: QuestionGenerationState,
    *,
    language: str,
    sample_cases: list[dict[str, Any]],
    hidden_cases: list[dict[str, Any]],
    strict_contract_guidance: str,
    language_contract_guidance: str,
) -> tuple[str, str]:
    system_prompt = build_task_system_prompt(
        role="independent testcase oracle engineer",
        objective=(
            "Write a correctness-first program that independently computes outputs "
            "from the problem contract for testcase quality control."
        ),
        rules=(
            (
                "Do not infer behavior from any current expected output or "
                "optimized solution."
            ),
            (
                "Prefer direct simulation or exhaustive logic when valid for "
                "supplied testcase sizes."
            ),
            (
                "The program must still implement the stated behavior, not "
                "hard-code outputs."
            ),
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Generate an independent brute-force oracle for the supplied inputs.",
        context={
            "problem_contract": {
                "title": state.get("title", ""),
                "problem_statement": state.get("problem_statement", ""),
                "input_format": state.get("input_format", ""),
                "input_explanation": state.get("input_explanation", ""),
                "output_format": state.get("output_format", ""),
                "output_explanation": state.get("output_explanation", ""),
                "constraints": state.get("constraints", ""),
            },
            "testcase_inputs": {
                "sample": [case.get("input", "") for case in sample_cases],
                "hidden": [case.get("input", "") for case in hidden_cases],
            },
            "oracle_language": language,
        },
        requirements=(
            strict_contract_guidance,
            language_contract_guidance,
            "Set reference_solution to complete source code only.",
            "Do not use, reproduce, or guess current expected outputs.",
            (
                "Set supported_languages to only oracle_language and "
                "reference_solutions to an empty object."
            ),
            "Describe the independent oracle method and its actual complexity.",
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_bruteforce_solution_prompt"]
