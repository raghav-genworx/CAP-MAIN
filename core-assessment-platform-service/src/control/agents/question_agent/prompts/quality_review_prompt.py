"""Prompt builder for the quality review agent."""

from __future__ import annotations

from ..states.question_state import QuestionGenerationState


def build_quality_review_prompt(state: QuestionGenerationState) -> tuple[str, str]:
    system_prompt = (
        "You are the quality review agent for a coding assessment platform. "
        "Score publish readiness, overall quality, and AI confidence, then "
        "provide recruiter-friendly next steps."
    )
    user_prompt = (
        f"Title: {state.get('title', '')}\n"
        f"Validation checks: "
        f"{', '.join(state.get('validation_checks', [])) or 'none'}\n"
        f"Validation warnings: "
        f"{', '.join(state.get('validation_warnings', [])) or 'none'}\n"
        f"Duplicate warnings: "
        f"{', '.join(state.get('duplicate_warnings', [])) or 'none'}\n"
        f"Sample tests: {len(state.get('sample_test_cases', []))}\n"
        f"Hidden tests: {len(state.get('hidden_test_cases', []))}\n"
        "Return a publish readiness score, quality score, confidence score, "
        "summary, and notes."
    )
    return system_prompt, user_prompt


__all__ = ["build_quality_review_prompt"]
