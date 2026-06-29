"""Multi language solution node for the question agent."""

from __future__ import annotations

import logging

from schemas.question_bank import (
    ReferenceSolutionArtifact,
    ValidationStatus,
)

from ..prompts.multi_language_solution_prompt import (
    build_focused_language_solution_prompt,
)
from ..states.question_state import (
    QuestionGenerationState,
    SolutionOutput,
)
from ..tools.question_tools import QuestionAgentToolsMixin

LOGGER = logging.getLogger(__name__)


class MultiLanguageSolutionNodeMixin(QuestionAgentToolsMixin):
    """Multi language solution node for the question agent."""

    def _multi_language_solution_node(
        self,
        state: QuestionGenerationState,
    ) -> QuestionGenerationState:
        """Generate and validate equivalent solutions after the primary passes."""

        solution_validation = state.get("solution_validation")
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

        primary_language = (
            state.get("reference_language", "python").strip().lower() or "python"
        )
        supported_languages = state.get("supported_languages", [primary_language])
        target_languages = [
            self._normalize_solution_language(language)
            for language in supported_languages
            if self._normalize_solution_language(language) != primary_language
        ]
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
                    primary_language=primary_language,
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
                report = self._validate_source_against_tests(
                    language=normalized_language,
                    source_code=sanitized_source,
                    sample_tests=sample_tests,
                    hidden_tests=hidden_tests,
                    rounds=[],
                    time_limit_seconds=state.get("execution_time_limit_seconds"),
                    memory_limit_kb=(state.get("memory_limit_mb", 256) * 1024),
                )
                validation_status = ValidationStatus(report.status)
                notes.append(report.summary)
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
        primary_language: str,
    ) -> str:
        system_prompt, user_prompt = build_focused_language_solution_prompt(
            state,
            target_language=target_language,
            primary_language=primary_language,
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
            schema_model=SolutionOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return self._ensure_runnable_reference_solution(
            state=state,
            candidate=model.reference_solution,
            language=target_language,
            schema_name=f"{target_language}_focused_solution_contract_retry",
            rejection_context=(
                f"Focused {target_language} generation did not satisfy the "
                "runnable-code contract."
            ),
        )


__all__ = ["MultiLanguageSolutionNodeMixin"]
