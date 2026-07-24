"""Duplicate detection node for the question agent."""

from __future__ import annotations

from ..prompts.duplicate_detection_prompt import build_duplicate_detection_prompt
from ..states.question_state import (
    DuplicateOutput,
    QuestionGenerationState,
)
from ..tools.question_tools import QuestionAgentToolsMixin


class DuplicateDetectionNodeMixin(QuestionAgentToolsMixin):
    """Duplicate detection node for the question agent."""

    def _duplicate_detection_node(
        self,
        state: QuestionGenerationState,
    ) -> QuestionGenerationState:
        """NODE 11/12 — checks the new question against the existing library.

        Reads: the finished draft + `existing_question_titles`/tags that were
        seeded into the state from the recruiter's current question bank.
        Does: one LLM call (-> `DuplicateOutput`) producing a similarity score
        and any duplicate warnings.
        Writes: `duplicate_warnings` (surfaced in the final quality summary).
        """

        system_prompt, user_prompt = build_duplicate_detection_prompt(state)
        model = self._structured_completion(
            schema_name="duplicate_detection",
            schema_model=DuplicateOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        notes = self._append_notes(state.get("notes", []), *model.notes)
        execution_history = self._append_notes(
            state.get("execution_history", []),
            "Duplicate Detection Agent: compared against question library",
        )
        return {
            "duplicate_warnings": model.duplicate_warnings,
            "notes": notes,
            "execution_history": execution_history,
        }


__all__ = ["DuplicateDetectionNodeMixin"]
