"""Prompt builder for the problem statement agent."""

from __future__ import annotations

from constants.question_tag_taxonomy import QUESTION_TAG_CATEGORIES

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
    if state.get("generation_scope") == "problem":
        system_prompt = build_task_system_prompt(
            role="coding-problem statement editor",
            objective=(
                "Write only the self-contained candidate-facing problem statement "
                "while preserving explicit recruiter facts."
            ),
            rules=(
                (
                    "Do not generate or revise the title, formats, constraints, "
                    "metadata, tests, or validation rules."
                ),
                (
                    "Describe the required behavior clearly without inventing "
                    "hidden requirements."
                ),
                "Use complete-program STDIN/STDOUT semantics, not function signatures.",
            ),
        )
        user_prompt = build_task_user_prompt(
            task="Generate or refine only the problem_statement field.",
            context={
                "recruiter_request": parse_recruiter_request(prompt),
                "title": title_hint or state.get("title", ""),
                "current_problem_statement": state.get("problem_statement", ""),
                "focus_tags": state.get("focus_tags", []),
            },
            requirements=(
                "Return only problem_statement and notes.",
                "Make the statement self-contained, precise, and candidate-facing.",
                (
                    "Do not include input format, output format, constraints, "
                    "examples, solutions, or metadata."
                ),
                "Use notes only for material assumptions or unresolved ambiguity.",
            ),
        )
        return system_prompt, user_prompt

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
            "allowed_tag_taxonomy": QUESTION_TAG_CATEGORIES,
            "answer_validation_modes": {
                "exact": "One canonical STDOUT string is required.",
                "unordered": (
                    "The same whitespace-separated output tokens may appear in "
                    "any order."
                ),
                "floating": ("Numeric outputs are accepted within a small tolerance."),
                "multiple_valid": (
                    "Several distinct raw outputs can be correct for the same input."
                ),
                "constructive": (
                    "The candidate must output any construction satisfying the "
                    "problem rules."
                ),
            },
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
                "Use concise machine-checkable constraints. Return topics as an "
                "empty list and use only exact, directly matching identifiers "
                "from allowed_tag_taxonomy for tags and category."
            ),
            (
                "Set answer_validation_mode to exact by default. Use unordered "
                "only when output order is irrelevant, floating only for numeric "
                "tolerance, multiple_valid only when several different outputs "
                "can satisfy one input, and constructive only for any-valid-"
                "construction problems."
            ),
            (
                "For unordered or floating, leave output_checker empty unless "
                "custom logic is truly required and explain the logic in "
                "output_checker_explanation."
            ),
            (
                "For multiple_valid or constructive, output_checker must be a "
                "safe Python function named check_output(stdin: str, "
                "expected_output: str, actual_output: str). It must be "
                "deterministic, use no imports, no file/network/process/input/"
                "print/eval/exec calls, and return bool or (bool, message)."
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


def build_checker_generation_prompt(
    problem_statement: str,
    input_format: str,
    output_format: str,
    constraints: str,
    mode: str,
) -> tuple[str, str]:
    system_prompt = (
        "You are an expert systems validation programmer. Your task is to generate "
        "a safe, deterministic Python function named check_output(stdin: str, "
        "expected_output: str, actual_output: str) -> bool | tuple[bool, str] that "
        "validates whether a candidate's actual_output satisfies all correctness rules "
        "for the given input."
    )
    user_prompt = (
        f"Problem Statement:\n{problem_statement}\n\n"
        f"Input Format:\n{input_format}\n\n"
        f"Output Format:\n{output_format}\n\n"
        f"Constraints:\n{constraints}\n\n"
        f"Answer Validation Mode: {mode}\n\n"
        "Requirements for the check_output function:\n"
        "1. The function must be named: check_output(stdin: str, expected_output: str, "
        "actual_output: str)\n"
        "2. It must return True (or (True, message)) if the actual_output is correct, "
        "and False (or (False, message)) if it is incorrect.\n"
        "3. Since the answer validation mode is constructive or multiple_valid, the "
        "expected_output is only a valid exemplar, NOT necessarily the only correct "
        "answer. You must validate actual_output directly against the rules described "
        "in the problem statement using stdin.\n"
        "4. The code must be self-contained: do not use imports, do not call print, "
        "eval, exec, open, input, or any other disallowed builtins.\n"
        "5. Make the validation parsing robust to whitespace/newlines.\n"
        "6. Provide a clear explanation of how the checker works in "
        "output_checker_explanation.\n\n"
        "Return the function code in the output_checker field, and the explanation "
        "in the output_checker_explanation field.\n"
    )
    return system_prompt, user_prompt


__all__ = ["build_problem_statement_prompt", "build_checker_generation_prompt"]
