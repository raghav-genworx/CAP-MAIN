"""Prompt builder for duplicate detection."""

from __future__ import annotations

from ..states.question_state import QuestionGenerationState


def build_duplicate_detection_prompt(
    state: QuestionGenerationState,
) -> tuple[str, str]:
    system_prompt = (
        "You are the duplicate detection agent for a coding assessment platform. "
        "Compare the draft against the recruiter's question library and warn "
        "about meaningful title, topic, tag, or concept overlap."
    )
    user_prompt = (
        f"Draft title: {state.get('title', '')}\n"
        f"Draft tags: {', '.join(state.get('tags', []))}\n"
        f"Existing titles: "
        f"{', '.join(state.get('existing_question_titles', [])) or 'none'}\n"
        f"Existing tags: "
        f"{', '.join(state.get('existing_question_tags', [])) or 'none'}\n"
        "Return any duplicate warnings and a similarity score between 0 and 1."
    )
    return system_prompt, user_prompt


__all__ = ["build_duplicate_detection_prompt"]
