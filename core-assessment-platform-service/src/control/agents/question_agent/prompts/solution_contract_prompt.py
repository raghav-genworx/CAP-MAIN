"""Shared prompt snippets for runnable reference-solution contracts."""

from __future__ import annotations

from typing import Any

from ..states.question_state import QuestionGenerationState


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
    system_prompt = (
        "You are correcting an invalid reference-solution response. Return valid "
        "JSON, but the `reference_solution` value itself must be complete, "
        "runnable source code in the requested language. Do not return algorithm "
        "names, explanations, markdown, TODOs, or pseudocode."
    )
    user_prompt = (
        f"{rejection_context}\n"
        f"Rejected answer:\n{source_code or '[empty]'}\n"
        f"Rejection reason: {rejection_reason}\n"
        f"Title: {state.get('title', '')}\n"
        f"Problem statement: {state.get('problem_statement', '')}\n"
        f"Constraints: {state.get('constraints', '')}\n"
        f"Input format: {state.get('input_format', '')}\n"
        f"Output format: {state.get('output_format', '')}\n"
        f"Sample tests: {sample_cases}\n"
        f"Hidden tests: {hidden_cases}\n"
        f"Reference language: {normalized_language}\n"
        f"{strict_solution_contract_guidance(normalized_language)} "
        f"{solution_contract_guidance(normalized_language)} "
        "For example, if the approach is Kadane's algorithm, write the actual "
        "loop-based implementation. Do not write only 'Kadane Algorithm'."
    )
    return system_prompt, user_prompt


__all__ = [
    "build_solution_contract_retry_prompt",
    "solution_contract_guidance",
    "strict_solution_contract_guidance",
]
