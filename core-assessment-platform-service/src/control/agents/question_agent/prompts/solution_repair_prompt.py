"""Prompt builder for reference-solution repair."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt
from .question_prompts import ADVERSARIAL_VALIDATION_ROUNDS


def build_solution_repair_prompt(
    state: QuestionGenerationState,
    *,
    source_code: str,
    sample_cases: list[dict[str, Any]],
    hidden_cases: list[dict[str, Any]],
    failing_results: list[dict[str, Any]],
    round_number: int,
    language: str,
    strict_contract_guidance: str,
    language_contract_guidance: str,
) -> tuple[str, str]:
    system_prompt = build_task_system_prompt(
        role="reference-solution debugger",
        objective=(
            "Repair the source against the authoritative problem contract while "
            "preserving already-correct behavior."
        ),
        rules=(
            (
                "Authority order is problem statement, constraints, I/O "
                "contract, then execution evidence."
            ),
            "Treat failures as diagnostic examples; never hard-code testcase answers.",
            "Keep the algorithm valid across the complete constrained domain.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Repair and generalize the current reference solution.",
        context={
            "qc_round": {
                "current": round_number,
                "maximum": ADVERSARIAL_VALIDATION_ROUNDS,
            },
            "problem_contract": {
                "title": state.get("title", ""),
                "problem_statement": state.get("problem_statement", ""),
                "input_format": state.get("input_format", ""),
                "output_format": state.get("output_format", ""),
                "constraints": state.get("constraints", ""),
            },
            "testcases": {"sample": sample_cases, "hidden": hidden_cases},
            "failing_execution_results": failing_results,
            "current_solution": {"language": language, "source_code": source_code},
        },
        requirements=(
            strict_contract_guidance,
            language_contract_guidance,
            "Set reference_solution to repaired complete source code only.",
            (
                "Set supported_languages to only the reference language and "
                "reference_solutions to an empty object."
            ),
            (
                "Fix the root cause indicated by failures without changing "
                "correct problem behavior."
            ),
            (
                "Return accurate approach and complexity metadata for the "
                "repaired implementation."
            ),
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_solution_repair_prompt"]
