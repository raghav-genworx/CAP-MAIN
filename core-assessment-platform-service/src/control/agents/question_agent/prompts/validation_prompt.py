"""Prompt builder for the validation agent."""

from __future__ import annotations

from schemas.question_bank import SolutionValidationReport

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt


def build_validation_prompt(
    state: QuestionGenerationState,
    *,
    solution_validation: SolutionValidationReport,
) -> tuple[str, str]:
    system_prompt = build_task_system_prompt(
        role="question publish-readiness validator",
        objective=(
            "Report factual completeness and consistency checks after source "
            "execution, without overriding execution results."
        ),
        rules=(
            "A passed check must name concrete evidence that is present.",
            "A warning must identify a specific defect and the required correction.",
            "Never mark source readiness when execution validation did not pass.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Summarize recruiter-facing validation checks and actionable warnings.",
        context={
            "draft_facts": {
                "title": state.get("title", ""),
                "difficulty": state.get("difficulty", "medium"),
                "problem_statement_present": bool(
                    state.get("problem_statement", "").strip()
                ),
                "input_format_present": bool(state.get("input_format", "").strip()),
                "output_format_present": bool(state.get("output_format", "").strip()),
                "constraints_present": bool(state.get("constraints", "").strip()),
                "reference_solution_present": bool(
                    state.get("reference_solution", "").strip()
                ),
                "sample_test_count": len(state.get("sample_test_cases", [])),
                "hidden_test_count": len(state.get("hidden_test_cases", [])),
            },
            "execution_validation": solution_validation,
        },
        requirements=(
            "List only verified positive checks in checks.",
            (
                "List each missing, contradictory, failed, skipped, or stale "
                "condition in warnings."
            ),
            (
                "Treat execution_validation.status as authoritative for solution "
                "readiness."
            ),
            (
                "Keep every item concise, factual, and actionable; avoid scores "
                "or generic praise."
            ),
            (
                "Use notes only for validation limitations not already "
                "represented by warnings."
            ),
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_validation_prompt"]
