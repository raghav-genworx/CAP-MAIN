"""Constraint-script validation node for generated test cases."""

from __future__ import annotations

import logging

from ..states.question_state import QuestionGenerationState
from ..tools.question_tools import QuestionAgentToolsMixin

LOGGER = logging.getLogger(__name__)


class ConstraintScriptNodeMixin(QuestionAgentToolsMixin):
    """Generate a Python constraint checker and repair rejected test cases."""

    def _constraint_script_node(
        self,
        state: QuestionGenerationState,
    ) -> QuestionGenerationState:
        """NODE 6/12 — programmatically checks that every testcase input is legal.

        Reads: sample + hidden test cases, plus the constraints.
        Does: asks the LLM to write a Python `validate_testcase(...)` function,
        runs it against each generated input, and for any input that violates
        the constraints it tries to generate a replacement (repair loop). This
        is the last gate before we spend effort generating/executing a solution.
        Writes: cleaned `sample_test_cases`/`hidden_test_cases`, the generated
        `constraint_validation_script`, and any warnings.
        """

        sample_tests = [
            case.model_copy(update={"is_sample": True})
            for case in self._complete_test_cases(state.get("sample_test_cases", []))
        ]
        raw_hidden_tests = [
            case.model_copy(update={"is_sample": False})
            for case in self._complete_test_cases(state.get("hidden_test_cases", []))
        ]
        hidden_tests = (
            [] if state.get("generation_scope") == "examples" else raw_hidden_tests
        )
        hidden_tests_for_failure = (
            raw_hidden_tests
            if state.get("generation_scope") == "examples"
            else hidden_tests
        )
        if not sample_tests and not hidden_tests:
            return {
                "constraint_validation_warnings": [
                    "Constraint script skipped because no complete test cases exist.",
                ],
                "execution_history": self._append_notes(
                    state.get("execution_history", []),
                    "Constraint Script Agent: skipped without complete tests",
                ),
            }

        warnings: list[str] = []
        try:
            script = self._generate_constraint_validation_script(state)
        except Exception as exc:  # pragma: no cover - network/model dependent
            LOGGER.warning("Constraint script generation failed: %s", exc)
            return {
                "sample_test_cases": sample_tests,
                "hidden_test_cases": hidden_tests_for_failure,
                "constraint_validation_script": "",
                "constraint_validation_warnings": [
                    f"Constraint script generation failed: {exc}",
                ],
                "notes": self._append_notes(
                    state.get("notes", []),
                    "Constraint script generation failed; tests need manual review.",
                ),
                "execution_history": self._append_notes(
                    state.get("execution_history", []),
                    "Constraint Script Agent: generation failed",
                ),
            }

        results = self._run_constraint_script_for_cases(
            script=script,
            sample_tests=sample_tests,
            hidden_tests=hidden_tests,
        )
        sample_rejections = [
            result
            for result in results
            if result["bucket"] == "sample" and not result["valid"]
        ]
        hidden_rejections = [
            result
            for result in results
            if result["bucket"] == "hidden" and not result["valid"]
        ]
        rejected_count = len(sample_rejections) + len(hidden_rejections)
        replaced_count = 0
        if rejected_count:
            sample_tests, hidden_tests, repair_warnings, replaced_count = (
                self._repair_constraint_invalid_test_cases(
                    state=state,
                    script=script,
                    sample_tests=sample_tests,
                    hidden_tests=hidden_tests,
                    sample_rejections=sample_rejections,
                    hidden_rejections=hidden_rejections,
                )
            )
            warnings.extend(repair_warnings)

        if rejected_count and replaced_count < rejected_count:
            warnings.append(
                (
                    "Constraint script could not replace every rejected testcase; "
                    "remaining rows need recruiter review."
                ),
            )
        summary = (
            "Constraint Script Agent: all generated tests passed constraints"
            if not rejected_count
            else (
                "Constraint Script Agent: replaced "
                f"{replaced_count}/{rejected_count} rejected testcase"
                f"{'' if rejected_count == 1 else 's'}"
            )
        )
        notes = list(state.get("notes", []))
        if rejected_count:
            notes.append(
                (
                    "Constraint script rejected "
                    f"{rejected_count} testcase"
                    f"{'' if rejected_count == 1 else 's'} and accepted "
                    f"{replaced_count} replacement"
                    f"{'' if replaced_count == 1 else 's'}."
                ),
            )

        return {
            "sample_test_cases": sample_tests,
            "hidden_test_cases": (
                raw_hidden_tests
                if state.get("generation_scope") == "examples"
                else hidden_tests
            ),
            "constraint_validation_script": script,
            "constraint_validation_warnings": warnings,
            "notes": notes,
            "execution_history": self._append_notes(
                state.get("execution_history", []),
                summary,
            ),
        }


__all__ = ["ConstraintScriptNodeMixin"]
