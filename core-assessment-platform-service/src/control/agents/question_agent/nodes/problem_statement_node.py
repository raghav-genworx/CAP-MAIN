"""Problem statement node for the question agent."""

from __future__ import annotations

from ..prompts.problem_statement_prompt import build_problem_statement_prompt
from ..states.question_state import (
    ProblemStatementOutput,
    QuestionGenerationState,
)
from ..tools.question_tools import QuestionAgentToolsMixin


class ProblemStatementNodeMixin(QuestionAgentToolsMixin):
    """Problem statement node for the question agent."""

    def _problem_statement_node(
        self,
        state: QuestionGenerationState,
    ) -> QuestionGenerationState:
        prompt = state["prompt"]
        title_hint = state.get("title_hint", "")
        system_prompt, user_prompt = build_problem_statement_prompt(
            state,
            prompt=prompt,
            title_hint=title_hint,
        )
        model = self._structured_completion(
            schema_name="problem_statement",
            schema_model=ProblemStatementOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        notes = self._append_notes(state.get("notes", []), *model.notes)
        execution_history = self._append_notes(
            state.get("execution_history", []),
            "Problem Statement Agent: generated title and statement",
        )
        return {
            "title": model.title.strip(),
            "problem_statement": model.problem_statement.strip(),
            "topics": self._normalize_tokens(
                model.topics or state.get("topics", []),
            ),
            "tags": self._normalize_tokens(model.tags or state.get("focus_tags", [])),
            "category": model.category.strip().lower() or state.get("category", ""),
            "input_format": model.input_format.strip(),
            "input_explanation": model.input_explanation.strip(),
            "output_format": model.output_format.strip(),
            "output_explanation": model.output_explanation.strip(),
            "constraints": model.constraints.strip() or state.get("constraints", ""),
            "sample_test_cases": [
                case.model_copy(update={"is_sample": True})
                for case in model.sample_test_cases
            ]
            or state.get("sample_test_cases", []),
            "notes": notes,
            "execution_history": execution_history,
        }


__all__ = ["ProblemStatementNodeMixin"]
