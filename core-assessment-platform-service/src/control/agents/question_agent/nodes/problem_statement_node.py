"""Problem statement node for the question agent."""

from __future__ import annotations

from constants.question_tag_taxonomy import (
    normalize_question_category,
    normalize_question_tags,
)
from core.services.question_bank.output_validation import (
    default_checker_explanation,
    normalize_answer_validation_mode,
)
from schemas.question_bank import AnswerValidationMode

from ..prompts.problem_statement_prompt import (
    build_checker_generation_prompt,
    build_problem_statement_prompt,
)
from ..states.question_state import (
    CheckerOutput,
    ProblemStatementOnlyOutput,
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
        """NODE 2/12 — turns the raw prompt into the problem spec.

        Reads: `prompt`, `title_hint`, `focus_tags`.
        Does: one LLM call (validated into `ProblemStatementOutput`) to produce
        the title, statement, input/output formats + explanations, initial
        constraints, tags/category, and the answer-validation mode. For
        non-exact answer modes (multiple valid / constructive) it makes a SECOND
        LLM call to generate a custom output-checker.
        Writes: title, problem_statement, formats, tags, category, checker,
        constraints, and initial sample_test_cases into the shared state.
        """

        prompt = state["prompt"]
        title_hint = state.get("title_hint", "")
        system_prompt, user_prompt = build_problem_statement_prompt(
            state,
            prompt=prompt,
            title_hint=title_hint,
        )
        if state.get("generation_scope") == "problem":
            statement_model = self._structured_completion(
                schema_name="problem_statement_only",
                schema_model=ProblemStatementOnlyOutput,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            return {
                "problem_statement": statement_model.problem_statement.strip(),
                "notes": self._append_notes(
                    state.get("notes", []),
                    *statement_model.notes,
                ),
                "execution_history": self._append_notes(
                    state.get("execution_history", []),
                    "Problem Statement Agent: generated only the problem statement",
                ),
            }

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
        tags = normalize_question_tags(
            [
                *model.tags,
                *model.topics,
                *state.get("focus_tags", []),
            ],
            limit=6,
        )
        answer_mode = AnswerValidationMode(
            normalize_answer_validation_mode(model.answer_validation_mode),
        )
        output_checker = model.output_checker.strip()
        output_checker_explanation = model.output_checker_explanation.strip()

        if answer_mode in {
            AnswerValidationMode.MULTIPLE_VALID,
            AnswerValidationMode.CONSTRUCTIVE,
        }:
            checker_system, checker_user = build_checker_generation_prompt(
                problem_statement=model.problem_statement,
                input_format=model.input_format,
                output_format=model.output_format,
                constraints=model.constraints or state.get("constraints", ""),
                mode=answer_mode.value,
            )
            checker_model = self._structured_completion(
                schema_name="output_checker",
                schema_model=CheckerOutput,
                system_prompt=checker_system,
                user_prompt=checker_user,
            )
            output_checker = checker_model.output_checker.strip()
            output_checker_explanation = (
                checker_model.output_checker_explanation.strip()
            )
            execution_history = self._append_notes(
                execution_history,
                "Problem Statement Agent: generated custom output checker "
                f"for mode {answer_mode.value}",
            )

        return {
            "title": model.title.strip(),
            "problem_statement": model.problem_statement.strip(),
            "topics": [],
            "tags": tags,
            "category": normalize_question_category(model.category, tags),
            "input_format": model.input_format.strip(),
            "input_explanation": model.input_explanation.strip(),
            "output_format": model.output_format.strip(),
            "output_explanation": model.output_explanation.strip(),
            "answer_validation_mode": answer_mode,
            "output_checker": output_checker,
            "output_checker_explanation": (
                output_checker_explanation or default_checker_explanation(answer_mode)
            ),
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
