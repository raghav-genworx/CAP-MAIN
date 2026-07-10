"""Constraint node for the question agent."""

from __future__ import annotations

from ..prompts.constraint_prompt import build_constraint_prompt
from ..states.question_state import (
    ConstraintOutput,
    QuestionGenerationState,
)
from ..tools.question_tools import QuestionAgentToolsMixin


class ConstraintNodeMixin(QuestionAgentToolsMixin):
    """Constraint node for the question agent."""

    def _constraint_node(
        self, state: QuestionGenerationState
    ) -> QuestionGenerationState:
        """NODE 3/12 — finalizes constraints and execution limits.

        Reads: the problem context built so far.
        Does: one LLM call (-> `ConstraintOutput`) to firm up the constraints
        text and the runtime budget (candidate solve time, per-execution time
        limit in seconds, memory limit in MB). May also tidy the I/O formats.
        Writes: constraints + the time/memory limits used later when the
        validation node actually executes the solution.
        """

        system_prompt, user_prompt = build_constraint_prompt(state)
        model = self._structured_completion(
            schema_name="constraints",
            schema_model=ConstraintOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        notes = self._append_notes(state.get("notes", []), *model.notes)
        execution_history = self._append_notes(
            state.get("execution_history", []),
            "Constraint Agent: shaped runtime and memory limits",
        )
        return {
            "input_format": model.input_format.strip() or state.get("input_format", ""),
            "input_explanation": "",
            "output_format": model.output_format.strip()
            or state.get("output_format", ""),
            "output_explanation": "",
            "constraints": model.constraints.strip(),
            "candidate_solve_time_minutes": model.candidate_solve_time_minutes
            or model.time_limit_minutes
            or state.get("candidate_solve_time_minutes", 45),
            "execution_time_limit_seconds": model.execution_time_limit_seconds
            or state.get("execution_time_limit_seconds", 2),
            "memory_limit_mb": model.memory_limit_mb
            or state.get("memory_limit_mb", 256),
            "notes": notes,
            "execution_history": execution_history,
        }


__all__ = ["ConstraintNodeMixin"]
