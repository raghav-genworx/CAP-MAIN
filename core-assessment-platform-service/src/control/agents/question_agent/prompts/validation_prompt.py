"""Prompt builder for the validation agent."""

from __future__ import annotations

from schemas.question_bank import SolutionValidationReport

from ..states.question_state import QuestionGenerationState


def build_validation_prompt(
    state: QuestionGenerationState,
    *,
    solution_validation: SolutionValidationReport,
) -> tuple[str, str]:
    system_prompt = (
        "You are the validation agent for a coding assessment platform. Review "
        "section completeness, internal consistency, test coverage signals, and "
        "reference-solution readiness after execution validation has run."
    )
    user_prompt = (
        f"Title: {state.get('title', '')}\n"
        f"Difficulty: {state.get('difficulty', 'medium')}\n"
        f"Sample tests: {len(state.get('sample_test_cases', []))}\n"
        f"Hidden tests: {len(state.get('hidden_test_cases', []))}\n"
        f"Constraints present: {bool(state.get('constraints', '').strip())}\n"
        f"Reference solution present: "
        f"{bool(state.get('reference_solution', '').strip())}\n"
        f"Execution validation summary: {solution_validation.summary}\n"
        f"Adversarial rounds: {len(solution_validation.rounds)}\n"
        "Return validation checks and warnings that are actionable for recruiter "
        "review."
    )
    return system_prompt, user_prompt


__all__ = ["build_validation_prompt"]
