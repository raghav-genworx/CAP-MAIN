"""Example node for the question agent."""

from __future__ import annotations

from ..prompts.example_prompt import build_example_prompt
from ..states.question_state import (
    ExampleOutput,
    QuestionGenerationState,
)
from ..tools.question_tools import QuestionAgentToolsMixin


class ExampleNodeMixin(QuestionAgentToolsMixin):
    """Example node for the question agent."""

    def _example_node(self, state: QuestionGenerationState) -> QuestionGenerationState:
        system_prompt, user_prompt = build_example_prompt(state)
        model = self._structured_completion(
            schema_name="examples",
            schema_model=ExampleOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        notes = self._append_notes(state.get("notes", []), *model.notes)
        execution_history = self._append_notes(
            state.get("execution_history", []),
            "Example Agent: generated sample test cases",
        )
        sample_test_cases = self._validate_test_cases_against_constraints(
            state=state,
            test_cases=[
                case.model_copy(update={"is_sample": True})
                for case in model.sample_test_cases
            ],
            bucket="sample",
        )
        return {
            "sample_test_cases": sample_test_cases,
            "notes": notes,
            "execution_history": execution_history,
        }


__all__ = ["ExampleNodeMixin"]
