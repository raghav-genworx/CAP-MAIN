"""Shared constants and prompt-facing summaries for the question agent."""

from __future__ import annotations

ADVERSARIAL_VALIDATION_ROUNDS = 3
ADVERSARIAL_TESTS_PER_ROUND = 2

SCOPE_NODE_SEQUENCE: dict[str, list[str]] = {
    "basics": ["problem_statement"],
    "problem": ["problem_statement"],
    "problem_field": ["problem_statement"],
    "constraints": ["constraints"],
    "constraints_formats": ["constraints"],
    "examples": ["examples", "constraint_script"],
    "tests": ["examples", "hidden_tests", "constraint_script"],
    "tests_solution": [
        "examples",
        "hidden_tests",
        "constraint_script",
        "solution",
        "validation",
    ],
    "solution": ["solution"],
    "other_languages": ["multi_language_solutions"],
    "recruiter_validation": ["validation"],
    "difficulty": ["metadata"],
    "metadata": ["metadata"],
}

SCOPE_SUMMARIES: dict[str, str] = {
    "basics": "Generated starter title/context from your description.",
    "problem": (
        "Generated the problem statement, I/O formats, and constraints from "
        "your description."
    ),
    "problem_field": (
        "Completed the requested problem section using the current context."
    ),
    "constraints": "Generated constraints from your description.",
    "constraints_formats": (
        "Generated input/output formats, explanations, constraints, and limits."
    ),
    "examples": "Generated and constraint-checked sample test cases.",
    "tests": "Generated and constraint-checked exact-count sample and hidden tests.",
    "tests_solution": (
        "Generated constraint-checked test cases, a reference solution, and validation."
    ),
    "solution": "Generated runnable primary reference solution code.",
    "other_languages": (
        "Generated and validated the requested non-primary language solutions."
    ),
    "recruiter_validation": (
        "Ran the validation gate for recruiter review using the current draft."
    ),
    "difficulty": "Classified difficulty, topics, and category from the final draft.",
    "metadata": "Classified difficulty, topics, and category from the final draft.",
}


__all__ = [
    "ADVERSARIAL_TESTS_PER_ROUND",
    "ADVERSARIAL_VALIDATION_ROUNDS",
    "SCOPE_NODE_SEQUENCE",
    "SCOPE_SUMMARIES",
]
