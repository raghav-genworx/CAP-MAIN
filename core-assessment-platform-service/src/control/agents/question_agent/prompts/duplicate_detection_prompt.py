"""Prompt builder for duplicate detection."""

from __future__ import annotations

from ..states.question_state import QuestionGenerationState
from .prompt_contract import build_task_system_prompt, build_task_user_prompt


def build_duplicate_detection_prompt(
    state: QuestionGenerationState,
) -> tuple[str, str]:
    system_prompt = build_task_system_prompt(
        role="question-library similarity reviewer",
        objective=(
            "Estimate duplicate risk from the supplied draft and library metadata "
            "without blocking legitimate variations."
        ),
        rules=(
            "Weight core task and required algorithm more than wording overlap.",
            (
                "Do not claim a duplicate when only a broad topic or generic "
                "title word matches."
            ),
            "Every warning must identify the specific overlapping evidence.",
        ),
    )
    user_prompt = build_task_user_prompt(
        task="Assess semantic duplicate risk against the existing question library.",
        context={
            "draft": {
                "title": state.get("title", ""),
                "problem_statement": state.get("problem_statement", ""),
                "topics": state.get("topics", []),
                "tags": state.get("tags", []),
                "solution_approach": state.get("solution_approach", ""),
            },
            "library": {
                "titles": state.get("existing_question_titles", []),
                "tags": state.get("existing_question_tags", []),
            },
        },
        requirements=(
            "Set similarity_score to 0..1, where 1 means the same underlying task.",
            (
                "Return an empty duplicate_warnings list when evidence is weak "
                "or the library is empty."
            ),
            (
                "Keep each warning concise and identify the matching title, "
                "concept, or algorithm evidence."
            ),
            "Use notes only for limitations caused by sparse library metadata.",
        ),
    )
    return system_prompt, user_prompt


__all__ = ["build_duplicate_detection_prompt"]
