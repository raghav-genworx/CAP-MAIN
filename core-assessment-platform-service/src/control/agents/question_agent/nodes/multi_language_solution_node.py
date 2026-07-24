"""Multi language solution node for the question agent."""

from __future__ import annotations

import logging

from schemas.question_bank import (
    ReferenceSolutionArtifact,
    SolutionValidationReport,
    TestCase,
    ValidationStatus,
)

from ..prompts.multi_language_solution_prompt import (
    build_focused_language_solution_prompt,
)
from ..prompts.question_prompts import ADVERSARIAL_VALIDATION_ROUNDS
from ..states.question_state import (
    FocusedLanguageSolutionOutput,
    QuestionGenerationState,
)
from ..tools.question_tools import QuestionAgentToolsMixin

LOGGER = logging.getLogger(__name__)


class MultiLanguageSolutionNodeMixin(QuestionAgentToolsMixin):
    """Multi language solution node for the question agent."""

    def _multi_language_solution_node(
        self,
        state: QuestionGenerationState,
    ) -> QuestionGenerationState:
        """NODE 9/12 — port the solution to the other supported languages.

        GUARD: this node no-ops unless the primary solution already PASSED
        validation (no point translating a broken solution).
        Does: for each requested non-primary language, generate a solution with
        an isolated LLM call, enforce the runnable-code contract, then validate
        and repair it against the same tests (`_validate_and_repair_language_solution`).
        Writes: additional entries in the `reference_solutions` map, each with
        its own per-language validation status. Like validation, it streams
        per-test progress over SSE.
        """

        solution_validation = state.get("solution_validation")
        validation_status = state.get("validation_status")
        validation_status_value = getattr(validation_status, "value", validation_status)
        if not solution_validation and validation_status_value == "passed":
            solution_validation = self._validate_reference_solution(state)
        if not solution_validation or solution_validation.status != "passed":
            return {
                "execution_history": self._append_notes(
                    state.get("execution_history", []),
                    (
                        "Multi-language Solution Agent: skipped until primary "
                        "solution passes"
                    ),
                ),
            }

        primary_language = self._normalize_solution_language(
            state.get("reference_language", "python"),
        )
        supported_languages = state.get("supported_languages", [primary_language])
        target_languages: list[str] = []
        requested_target = self._normalize_solution_language(
            state.get("target_language", ""),
        )
        requested_languages = (
            [requested_target]
            if state.get("target_language", "").strip()
            else supported_languages
        )
        for language in requested_languages:
            normalized_language = self._normalize_solution_language(language)
            if (
                normalized_language != primary_language
                and normalized_language not in target_languages
            ):
                target_languages.append(normalized_language)
        if not target_languages:
            return {
                "execution_history": self._append_notes(
                    state.get("execution_history", []),
                    "Multi-language Solution Agent: no additional languages requested",
                ),
            }

        reference_solutions = dict(state.get("reference_solutions", {}))
        sample_tests = self._complete_test_cases(state.get("sample_test_cases", []))
        hidden_tests = self._complete_test_cases(state.get("hidden_test_cases", []))
        node_notes: list[str] = []
        for normalized_language in target_languages:
            notes: list[str] = []
            try:
                source = self._generate_single_language_solution(
                    state=state,
                    target_language=normalized_language,
                )
                notes.append(
                    "Generated with an isolated per-language AI request.",
                )
                node_notes.append(
                    f"{normalized_language.upper()} solution generated separately.",
                )
            except Exception as exc:  # pragma: no cover - network/model dependent
                LOGGER.warning(
                    "Focused %s solution generation failed: %s",
                    normalized_language,
                    exc,
                )
                reference_solutions[normalized_language] = ReferenceSolutionArtifact(
                    language=normalized_language,
                    source_code="",
                    validation_status=ValidationStatus.SKIPPED,
                    time_complexity=state.get("time_complexity", ""),
                    space_complexity=state.get("space_complexity", ""),
                    notes=[f"Generation failed: {exc}"],
                )
                continue

            sanitized_source = self._sanitize_reference_solution(source)
            contract_error = self._reference_solution_contract_error(
                sanitized_source,
                normalized_language,
            )
            if contract_error:
                try:
                    sanitized_source = self._ensure_runnable_reference_solution(
                        state=state,
                        candidate=sanitized_source,
                        language=normalized_language,
                        schema_name=f"{normalized_language}_solution_contract_retry",
                        rejection_context=(
                            f"{normalized_language} solution generation did not "
                            "satisfy the runnable-code contract."
                        ),
                    )
                    notes.append("Regenerated because the first answer was not code.")
                except Exception as exc:  # pragma: no cover - network/model dependent
                    LOGGER.warning(
                        (
                            "Rejected generated %s solution because it is not "
                            "runnable code: %s"
                        ),
                        normalized_language,
                        contract_error,
                    )
                    reference_solutions[normalized_language] = (
                        ReferenceSolutionArtifact(
                            language=normalized_language,
                            source_code=sanitized_source,
                            validation_status=ValidationStatus.SKIPPED,
                            time_complexity=state.get("time_complexity", ""),
                            space_complexity=state.get("space_complexity", ""),
                            notes=[contract_error, f"Regeneration failed: {exc}"],
                        )
                    )
                    continue
            try:
                sanitized_source, report, repair_notes = (
                    self._validate_and_repair_language_solution(
                        state=state,
                        target_language=normalized_language,
                        source_code=sanitized_source,
                        sample_tests=sample_tests,
                        hidden_tests=hidden_tests,
                    )
                )
                validation_status = ValidationStatus(report.status)
                notes.extend(repair_notes)
            except Exception as exc:  # pragma: no cover - execution service dependent
                LOGGER.warning(
                    "Validation failed for generated %s solution: %s",
                    normalized_language,
                    exc,
                )
                validation_status = ValidationStatus.SKIPPED
                notes.append(f"Validation skipped: {exc}")
            reference_solutions[normalized_language] = ReferenceSolutionArtifact(
                language=normalized_language,
                source_code=sanitized_source,
                validation_status=validation_status,
                time_complexity=state.get("time_complexity", ""),
                space_complexity=state.get("space_complexity", ""),
                notes=notes,
            )

        return {
            "reference_solutions": reference_solutions,
            "solution_validation": solution_validation,
            "validation_status": solution_validation.status,
            "notes": self._append_notes(state.get("notes", []), *node_notes),
            "execution_history": self._append_notes(
                state.get("execution_history", []),
                (
                    "Multi-language Solution Agent: generated and validated "
                    "requested languages"
                ),
            ),
        }

    def _generate_single_language_solution(
        self,
        *,
        state: QuestionGenerationState,
        target_language: str,
    ) -> str:
        system_prompt, user_prompt = build_focused_language_solution_prompt(
            state,
            target_language=target_language,
            sample_cases=self._prompt_cases(state.get("sample_test_cases", [])),
            hidden_cases=self._prompt_cases(state.get("hidden_test_cases", [])),
            strict_contract_guidance=self._strict_solution_contract_guidance(
                target_language,
            ),
            language_contract_guidance=self._solution_contract_guidance(
                target_language,
            ),
        )
        model = self._structured_completion(
            schema_name=f"{target_language}_reference_solution",
            schema_model=FocusedLanguageSolutionOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return self._ensure_runnable_reference_solution(
            state=state,
            candidate=model.source_code,
            language=target_language,
            schema_name=f"{target_language}_focused_solution_contract_retry",
            rejection_context=(
                f"Focused {target_language} generation did not satisfy the "
                "runnable-code contract."
            ),
        )

    def _validate_and_repair_language_solution(
        self,
        *,
        state: QuestionGenerationState,
        target_language: str,
        source_code: str,
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
    ) -> tuple[str, SolutionValidationReport, list[str]]:
        """Validate a translated solution and repair only the translated source."""

        time_limit_seconds = state.get("execution_time_limit_seconds")
        memory_limit_kb = state.get("memory_limit_mb", 256) * 1024
        notes: list[str] = []
        current_source = source_code
        report = self._validate_source_against_tests(
            language=target_language,
            source_code=current_source,
            sample_tests=sample_tests,
            hidden_tests=hidden_tests,
            rounds=[],
            time_limit_seconds=time_limit_seconds,
            memory_limit_kb=memory_limit_kb,
            **self._answer_validation_kwargs(state),
        )
        notes.append(report.summary)

        for round_number in range(1, ADVERSARIAL_VALIDATION_ROUNDS + 1):
            if report.status == "passed":
                return current_source, report, notes

            repair_state: QuestionGenerationState = {
                **state,
                "reference_language": target_language,
                "reference_solution": current_source,
                "supported_languages": [target_language],
            }
            repaired_source = self._repair_reference_solution(
                state=repair_state,
                source_code=current_source,
                validation_report=report,
                sample_tests=sample_tests,
                hidden_tests=hidden_tests,
                round_number=round_number,
            )
            repaired_source = self._sanitize_reference_solution(repaired_source)
            if not repaired_source.strip():
                notes.append(
                    (
                        f"Repair round {round_number} produced no "
                        f"{target_language} source."
                    ),
                )
                return current_source, report, notes
            if repaired_source.strip() == current_source.strip():
                notes.append(
                    (
                        f"Repair round {round_number} did not change the "
                        f"{target_language} source."
                    ),
                )
                return current_source, report, notes

            current_source = repaired_source
            notes.append(
                f"Repair round {round_number} updated the {target_language} source.",
            )
            report = self._validate_source_against_tests(
                language=target_language,
                source_code=current_source,
                sample_tests=sample_tests,
                hidden_tests=hidden_tests,
                rounds=[],
                time_limit_seconds=time_limit_seconds,
                memory_limit_kb=memory_limit_kb,
                **self._answer_validation_kwargs(state),
            )
            notes.append(report.summary)

        return current_source, report, notes


__all__ = ["MultiLanguageSolutionNodeMixin"]
