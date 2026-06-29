"""Metadata node for the question agent."""

from __future__ import annotations

from schemas.question_bank import (
    DifficultySource,
    MetadataStatus,
)

from ..prompts.metadata_prompt import build_metadata_prompt
from ..states.question_state import (
    MetadataOutput,
    QuestionGenerationState,
)
from ..tools.question_tools import QuestionAgentToolsMixin


class MetadataNodeMixin(QuestionAgentToolsMixin):
    """Metadata node for the question agent."""

    def _metadata_node(self, state: QuestionGenerationState) -> QuestionGenerationState:
        system_prompt, user_prompt = build_metadata_prompt(
            state,
            sample_cases=self._prompt_cases(state.get("sample_test_cases", [])),
            hidden_cases=self._prompt_cases(state.get("hidden_test_cases", [])),
            validation_summary=self._validation_summary(state),
        )
        model = self._structured_completion(
            schema_name="metadata",
            schema_model=MetadataOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        notes = self._append_notes(state.get("notes", []), *model.notes)
        execution_history = self._append_notes(
            state.get("execution_history", []),
            "Metadata Classifier Agent: classified difficulty, topics, and category",
        )
        return {
            "difficulty": model.difficulty.value,
            "topics": self._normalize_tokens(model.topics),
            "tags": self._normalize_tokens(model.tags),
            "category": model.category.strip().lower(),
            "expected_solve_time_minutes": model.expected_solve_time_minutes,
            "candidate_solve_time_minutes": model.expected_solve_time_minutes,
            "metadata_status": MetadataStatus.CLASSIFIED.value,
            "difficulty_source": DifficultySource.AI.value,
            "solution_approach": model.solution_approach.strip(),
            "time_complexity": model.time_complexity.strip(),
            "space_complexity": model.space_complexity.strip(),
            "notes": notes,
            "execution_history": execution_history,
        }


__all__ = ["MetadataNodeMixin"]
