"""Validation node for the question agent."""

from __future__ import annotations

from schemas.question_bank import ReferenceSolutionArtifact, ValidationStatus

from ..prompts.validation_prompt import build_validation_prompt
from ..states.question_state import (
    QuestionGenerationState,
    ValidationOutput,
)
from ..tools.question_tools import QuestionAgentToolsMixin


class ValidationNodeMixin(QuestionAgentToolsMixin):
    """Validation node for the question agent."""

    def _normalize_expected_outputs_with_oracle(
        self,
        state: QuestionGenerationState,
    ) -> QuestionGenerationState:
        """Return oracle-normalized tests in the concrete graph implementation."""

        raise NotImplementedError

    def _validation_node(
        self, state: QuestionGenerationState
    ) -> QuestionGenerationState:
        """NODE 8/12 — the correctness gate. This is where code is EXECUTED.

        Three phases:
          1. Oracle normalization (`_normalize_expected_outputs_with_oracle`):
             build an independent brute-force solution and use its output to fix
             any wrong expected outputs in the tests.
          2. Adversarial loop (`_run_adversarial_solution_loop`): actually run
             the reference solution against all tests via the execution adapter,
             generate adversarial tests, and repair the solution across rounds.
          3. LLM consistency review (-> `ValidationOutput`) that turns the
             execution results into human-readable checks/warnings.
        Writes: possibly-repaired `reference_solution`/tests, plus
        `validation_status`, `solution_validation` (per-test report), checks and
        warnings. This node's per-test progress is what the SSE stream shows.
        """

        oracle_patch = self._normalize_expected_outputs_with_oracle(state)
        validation_state: QuestionGenerationState = {
            **state,
            **oracle_patch,
        }
        loop_result = self._run_adversarial_solution_loop(validation_state)
        solution_validation = loop_result["solution_validation"]
        system_prompt, user_prompt = build_validation_prompt(
            validation_state,
            solution_validation=solution_validation,
        )
        model = self._structured_completion(
            schema_name="validation",
            schema_model=ValidationOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        checks = list(model.checks)
        warnings = list(model.warnings)
        if solution_validation.status == "passed":
            checks.append(
                (
                    "Reference solution passed execution validation on all "
                    "generated tests."
                ),
            )
        elif solution_validation.status == "failed":
            warnings.append(solution_validation.summary)
        elif solution_validation.status == "skipped":
            warnings.extend(
                solution_validation.runner_notes[:1] or [solution_validation.summary],
            )

        notes = self._append_notes(validation_state.get("notes", []), *model.notes)
        execution_history = self._append_notes(
            validation_state.get("execution_history", []),
            "Validation Agent: completed consistency review",
            f"Execution Validation: {solution_validation.summary}",
        )
        primary_language = self._normalize_solution_language(
            validation_state.get("reference_language", "python"),
        )
        reference_solutions = dict(validation_state.get("reference_solutions", {}))
        if loop_result["reference_solution"].strip():
            reference_solutions[primary_language] = ReferenceSolutionArtifact(
                language=primary_language,
                source_code=loop_result["reference_solution"],
                validation_status=ValidationStatus(solution_validation.status),
                time_complexity=validation_state.get("time_complexity", ""),
                space_complexity=validation_state.get("space_complexity", ""),
            )
        return {
            "reference_solution": loop_result["reference_solution"],
            "reference_solutions": reference_solutions,
            "sample_test_cases": loop_result["sample_test_cases"],
            "hidden_test_cases": loop_result["hidden_test_cases"],
            "validation_checks": checks,
            "validation_warnings": warnings,
            "validation_status": solution_validation.status,
            "solution_validation": solution_validation,
            "notes": notes,
            "execution_history": execution_history,
        }


__all__ = ["ValidationNodeMixin"]
