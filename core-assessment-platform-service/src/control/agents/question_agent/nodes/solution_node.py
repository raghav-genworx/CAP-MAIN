"""Solution node for the question agent."""

from __future__ import annotations

from schemas.question_bank import ReferenceSolutionArtifact

from ..prompts.solution_prompt import build_solution_prompt
from ..states.question_state import (
    QuestionGenerationState,
    SolutionOutput,
)
from ..tools.question_tools import QuestionAgentToolsMixin


class SolutionNodeMixin(QuestionAgentToolsMixin):
    """Solution node for the question agent."""

    def _solution_node(self, state: QuestionGenerationState) -> QuestionGenerationState:
        reference_language = state.get("reference_language", "python")
        system_prompt, user_prompt = build_solution_prompt(
            state,
            reference_language=reference_language,
            sample_cases=self._prompt_cases(state.get("sample_test_cases", [])),
            hidden_cases=self._prompt_cases(state.get("hidden_test_cases", [])),
            strict_contract_guidance=self._strict_solution_contract_guidance(
                reference_language,
            ),
            language_contract_guidance=self._solution_contract_guidance(
                reference_language,
            ),
        )
        model = self._structured_completion(
            schema_name="solution",
            schema_model=SolutionOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        reference_solution = self._ensure_runnable_reference_solution(
            state=state,
            candidate=model.reference_solution,
            language=reference_language,
            schema_name="solution_contract_retry",
            rejection_context=(
                "Initial solution generation did not satisfy the runnable-code "
                "contract."
            ),
        )
        notes = self._append_notes(state.get("notes", []), *model.notes)
        execution_history = self._append_notes(
            state.get("execution_history", []),
            "Solution Agent: created CodeChef-style reference implementation",
        )
        primary_language = reference_language.strip().lower() or "python"
        reference_solutions = dict(state.get("reference_solutions", {}))
        reference_solutions[primary_language] = ReferenceSolutionArtifact(
            language=primary_language,
            source_code=reference_solution,
            time_complexity=model.time_complexity.strip(),
            space_complexity=model.space_complexity.strip(),
            notes=model.notes,
        )
        return {
            "reference_solution": reference_solution,
            "reference_solutions": reference_solutions,
            "supported_languages": self._normalize_languages(
                model.supported_languages,
                reference_language,
                state["generation_settings"].supported_languages,
            ),
            "solution_approach": model.solution_approach.strip(),
            "time_complexity": model.time_complexity.strip(),
            "space_complexity": model.space_complexity.strip(),
            "notes": notes,
            "execution_history": execution_history,
        }


__all__ = ["SolutionNodeMixin"]
