"""Quality review node for the question agent."""

from __future__ import annotations

from ..prompts.quality_review_prompt import build_quality_review_prompt
from ..states.question_state import (
    QualityOutput,
    QuestionGenerationState,
)
from ..tools.question_tools import QuestionAgentToolsMixin


class QualityReviewNodeMixin(QuestionAgentToolsMixin):
    """Quality review node for the question agent."""

    def _quality_review_node(
        self, state: QuestionGenerationState
    ) -> QuestionGenerationState:
        system_prompt, user_prompt = build_quality_review_prompt(state)
        model = self._structured_completion(
            schema_name="quality_review",
            schema_model=QualityOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        notes = self._append_notes(state.get("notes", []), *model.notes)
        execution_history = self._append_notes(
            state.get("execution_history", []),
            "Quality Review Agent: generated publish readiness score",
        )
        summary = model.summary.strip()
        if state.get("duplicate_warnings"):
            summary = f"{summary} Duplicate review required."
        return {
            "quality_score": model.quality_score,
            "readiness_score": model.readiness_score,
            "ai_confidence_score": model.ai_confidence_score,
            "summary": summary,
            "notes": notes,
            "execution_history": execution_history,
        }


__all__ = ["QualityReviewNodeMixin"]
