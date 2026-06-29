"""Prompt builder for the quality review agent."""

from __future__ import annotations

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt


def build_quality_review_prompt(state: QuestionGenerationState) -> tuple[str, str]:
    system_prompt = build_task_system_prompt(
        role="final question quality reviewer",
        objective=(
            "Score final draft quality, publish readiness, and evidence confidence "
            "from the supplied validation facts."
        ),
        rules=(
            "Scores must decrease for unresolved validation or duplicate warnings.",
            (
                "Readiness measures publishability; quality measures artifact "
                "strength; confidence measures evidence strength."
            ),
            "Do not infer checks that are absent from context.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Produce the final evidence-based quality review.",
        context={
            "title": state.get("title", ""),
            "validation_status": state.get("validation_status", "not_run"),
            "validation_checks": state.get("validation_checks", []),
            "validation_warnings": state.get("validation_warnings", []),
            "duplicate_warnings": state.get("duplicate_warnings", []),
            "sample_test_count": len(state.get("sample_test_cases", [])),
            "hidden_test_count": len(state.get("hidden_test_cases", [])),
        },
        requirements=(
            (
                "Return integer quality_score, readiness_score, and "
                "ai_confidence_score in 0..100."
            ),
            "Do not give readiness above 69 when execution validation is not passed.",
            "Summarize the most important publish decision in one concise sentence.",
            (
                "Use notes for prioritized corrective actions only; return an "
                "empty list when none are needed."
            ),
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_quality_review_prompt"]
