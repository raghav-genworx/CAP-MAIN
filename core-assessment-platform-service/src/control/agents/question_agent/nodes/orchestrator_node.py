"""Orchestrator node for the question agent."""

from __future__ import annotations

from ..states.question_state import QuestionGenerationState
from ..tools.question_tools import QuestionAgentToolsMixin


class OrchestratorNodeMixin(QuestionAgentToolsMixin):
    """Orchestrator node for the question agent."""

    def _orchestrator_node(
        self, state: QuestionGenerationState
    ) -> QuestionGenerationState:
        orchestration_note = (
            "Orchestrator is sequencing problem, constraint, example, "
            "test, and review agents for "
            f"{state.get('generation_scope', 'full')} generation."
        )
        notes = self._append_notes(
            state.get("notes", []),
            orchestration_note,
        )
        execution_history = self._append_notes(
            state.get("execution_history", []),
            "Orchestrator: pipeline planned",
        )
        return {
            "notes": notes,
            "execution_history": execution_history,
        }


__all__ = ["OrchestratorNodeMixin"]
