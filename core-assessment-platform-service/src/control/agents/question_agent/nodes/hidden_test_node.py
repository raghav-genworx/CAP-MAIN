"""Hidden test node for the question agent."""

from __future__ import annotations

from ..prompts.hidden_test_prompt import build_hidden_test_prompt
from ..states.question_state import (
    HiddenTestOutput,
    QuestionGenerationState,
)
from ..tools.question_tools import QuestionAgentToolsMixin


class HiddenTestNodeMixin(QuestionAgentToolsMixin):
    """Hidden test node for the question agent."""

    def _hidden_test_node(
        self, state: QuestionGenerationState
    ) -> QuestionGenerationState:
        system_prompt, user_prompt = build_hidden_test_prompt(
            state,
            sample_cases=self._prompt_cases(state.get("sample_test_cases", [])),
        )
        model = self._structured_completion(
            schema_name="hidden_tests",
            schema_model=HiddenTestOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        notes = self._append_notes(state.get("notes", []), *model.notes)
        execution_history = self._append_notes(
            state.get("execution_history", []),
            "Test Case Agent: generated hidden, edge, and stress tests",
        )
        hidden_test_cases = self._validate_test_cases_against_constraints(
            state=state,
            test_cases=[
                case.model_copy(update={"is_sample": False})
                for case in model.hidden_test_cases
            ],
            bucket="hidden",
        )
        return {
            "hidden_test_cases": hidden_test_cases,
            "notes": notes,
            "execution_history": execution_history,
        }


__all__ = ["HiddenTestNodeMixin"]
