"""Shared prompt snippets for runnable reference-solution contracts."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt


def strict_solution_contract_guidance(normalized_language: str) -> str:
    return (
        "Hard requirements for `reference_solution`: return actual "
        f"{normalized_language} source code only; include imports/includes, a "
        "dedicated solve helper, and a main runner that reads the full STDIN and "
        "prints only the answer to STDOUT; do not include markdown fences, prose, "
        "TODOs, algorithm names, or labels such as 'Kadane Algorithm'."
    )


def solution_contract_guidance(language: str) -> str:
    contracts = {
        "python": (
            "Define the core logic in `def solve(raw_input: str) -> str:` and "
            'include `if __name__ == "__main__":` to print the returned string.'
        ),
        "java": (
            "Define `static String solve(String rawInput)` inside `class Main` "
            "and make `main` read full stdin and print the returned string."
        ),
        "cpp": (
            "Define `std::string solve(const std::string& raw_input)` and make "
            "`main()` read full stdin and print the returned string."
        ),
        "c": (
            "Define a dedicated solve function and include a `main()` runner that "
            "reads stdin and prints the computed output."
        ),
    }
    return contracts.get(
        language.strip().lower(),
        (
            "Return runnable source code with a dedicated solve function and a "
            "main runner."
        ),
    )


def build_solution_contract_retry_prompt(
    state: QuestionGenerationState,
    *,
    rejection_context: str,
    source_code: str,
    rejection_reason: str,
    normalized_language: str,
    sample_cases: list[dict[str, Any]],
    hidden_cases: list[dict[str, Any]],
) -> tuple[str, str]:
    system_prompt = build_task_system_prompt(
        role="source-code contract corrector",
        objective=(
            "Replace an invalid solution response with complete runnable source "
            "code in the requested language."
        ),
        rules=(
            "Correct only the response-contract and source completeness defect.",
            "Preserve the intended problem behavior and full-domain correctness.",
            (
                "Never return pseudocode, markdown fences, TODOs, or an "
                "algorithm name as source."
            ),
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Regenerate the rejected response as a runnable reference solution.",
        context={
            "rejection": {
                "context": rejection_context,
                "reason": rejection_reason,
                "rejected_source": source_code,
            },
            "problem_contract": {
                "title": state.get("title", ""),
                "problem_statement": state.get("problem_statement", ""),
                "input_format": state.get("input_format", ""),
                "output_format": state.get("output_format", ""),
                "constraints": state.get("constraints", ""),
            },
            "testcases": {"sample": sample_cases, "hidden": hidden_cases},
            "reference_language": normalized_language,
        },
        requirements=(
            strict_solution_contract_guidance(normalized_language),
            solution_contract_guidance(normalized_language),
            "Set reference_solution to complete source code only.",
            (
                "Set supported_languages to only reference_language and "
                "reference_solutions to an empty object."
            ),
            (
                "Return approach and complexity metadata that describes the "
                "regenerated source."
            ),
        ),
    )
    return system_prompt, user_prompt


__all__ = [
    "build_solution_contract_retry_prompt",
    "solution_contract_guidance",
    "strict_solution_contract_guidance",
]
