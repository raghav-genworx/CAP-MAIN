"""Shared utility helpers for the question agent."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from handlers.http_clients.ai_gateway import AIGatewayService
from schemas.question_bank import (
    SolutionValidationReport,
    SolutionValidationRound,
    TestCase,
)

from ..prompts.guardrail_prompt import build_guarded_system_prompt
from ..prompts.solution_contract_prompt import (
    build_solution_contract_retry_prompt,
    solution_contract_guidance,
    strict_solution_contract_guidance,
)
from ..states.question_state import QuestionGenerationState, SolutionOutput


class QuestionAgentUtilsMixin:
    """Utility methods shared across graph, node, and tool mixins."""

    _ai_gateway: AIGatewayService
    _current_recruiter_uid: str
    _current_workflow_mode: str

    @staticmethod
    def _complete_test_cases(test_cases: list[TestCase]) -> list[TestCase]:
        return [case for case in test_cases if case.expected_output.strip()]

    @staticmethod
    def _prompt_cases(test_cases: Any) -> list[dict[str, Any]]:
        return [case.model_dump() for case in test_cases or []]

    @staticmethod
    def _validation_summary(state: QuestionGenerationState) -> str:
        validation = state.get("solution_validation")
        return validation.summary if validation else "not run"

    def _ensure_runnable_reference_solution(
        self,
        *,
        state: QuestionGenerationState,
        candidate: str,
        language: str,
        schema_name: str,
        rejection_context: str,
    ) -> str:
        """Reject algorithm-name answers and retry until source code is returned."""

        normalized_language = self._normalize_solution_language(language)
        source_code = self._sanitize_reference_solution(candidate)
        contract_error = self._reference_solution_contract_error(
            source_code,
            normalized_language,
        )
        if not contract_error:
            return source_code

        last_error = contract_error
        for attempt in range(1, 3):
            system_prompt, user_prompt = build_solution_contract_retry_prompt(
                state,
                rejection_context=rejection_context,
                source_code=source_code,
                rejection_reason=last_error,
                normalized_language=normalized_language,
                sample_cases=self._prompt_cases(state.get("sample_test_cases", [])),
                hidden_cases=self._prompt_cases(state.get("hidden_test_cases", [])),
            )
            model = self._structured_completion(
                schema_name=f"{schema_name}_{attempt}",
                schema_model=SolutionOutput,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            source_code = self._sanitize_reference_solution(model.reference_solution)
            contract_error = self._reference_solution_contract_error(
                source_code,
                normalized_language,
            )
            if not contract_error:
                return source_code
            last_error = contract_error

        raise ValueError(
            f"Reference solution generation returned non-code output: {last_error}",
        )

    @classmethod
    def _source_contract_failure_report(
        cls,
        *,
        language: str,
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
        rounds: list[SolutionValidationRound],
        contract_error: str,
    ) -> SolutionValidationReport:
        total_tests = len(sample_tests) + len(hidden_tests)
        normalized_language = cls._normalize_solution_language(language)
        return SolutionValidationReport(
            status="failed",
            summary=(
                f"Reference solution is not complete runnable "
                f"{normalized_language} source code."
            ),
            passed_count=0,
            failed_count=total_tests,
            sample_count=len(sample_tests),
            hidden_count=len(hidden_tests),
            runner_notes=[
                contract_error,
                (
                    "Expected complete CodeChef-style source code with a solve "
                    "helper and stdin/stdout runner, not an algorithm name or "
                    "written explanation."
                ),
            ],
            results=[],
            rounds=rounds,
        )

    @staticmethod
    def _sanitize_reference_solution(value: str) -> str:
        stripped = value.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 3:
                return "\n".join(lines[1:-1]).strip()
        return stripped

    @staticmethod
    def _normalize_solution_language(language: str) -> str:
        normalized = language.strip().lower()
        if normalized in {"py", "python3"}:
            return "python"
        if normalized in {"c++", "cplusplus"}:
            return "cpp"
        return normalized or "python"

    @classmethod
    def _reference_solution_contract_error(cls, source_code: str, language: str) -> str:
        stripped = cls._sanitize_reference_solution(source_code)
        if not stripped:
            return "The reference_solution field is empty."

        normalized_language = cls._normalize_solution_language(language)
        lower_source = stripped.lower()
        forbidden_markers = [
            "todo",
            "pseudocode",
            "algorithm:",
            "approach:",
            "complexity:",
            "not implemented",
        ]
        if any(marker in lower_source for marker in forbidden_markers):
            return (
                "The reference_solution contains explanation/TODO text instead "
                "of final runnable source code."
            )

        preferred_markers = {
            "python": ["def solve", "__main__"],
            "java": ["class main", "public static void main", "solve("],
            "cpp": ["#include", "int main", "solve("],
            "c": ["#include", "int main", "solve("],
            "javascript": ["function solve", "process.stdin"],
            "js": ["function solve", "process.stdin"],
        }
        direct_program_markers = {
            "python": [
                ["import sys", "print("],
                ["sys.stdin", "print("],
                ["open(0", "print("],
                ["input(", "print("],
            ],
            "java": [["class main", "public static void main"]],
            "cpp": [["#include", "int main"]],
            "c": [["#include", "int main"]],
            "javascript": [["process.stdin", "console.log"]],
            "js": [["process.stdin", "console.log"]],
        }
        markers = preferred_markers.get(normalized_language, ["solve", "main"])
        has_preferred_markers = all(marker in lower_source for marker in markers)
        has_direct_program_markers = any(
            all(marker in lower_source for marker in marker_group)
            for marker_group in direct_program_markers.get(normalized_language, [])
        )
        if has_preferred_markers or has_direct_program_markers:
            return ""

        plain_text_indicators = [
            "algorithm",
            "use ",
            "using ",
            "sort the",
            "dynamic programming",
            "kadane",
            "two pointer",
            "binary search",
        ]
        if len(stripped.splitlines()) <= 2 or any(
            indicator in lower_source for indicator in plain_text_indicators
        ):
            return (
                "The reference_solution appears to be an algorithm name or "
                "plain-English approach, not source code."
            )

        return (
            "The reference_solution is missing runnable stdin/stdout program "
            "markers for the selected language."
        )

    @classmethod
    def _strict_solution_contract_guidance(cls, language: str) -> str:
        normalized_language = cls._normalize_solution_language(language)
        return strict_solution_contract_guidance(normalized_language)

    @staticmethod
    def _solution_contract_guidance(language: str) -> str:
        return solution_contract_guidance(language)

    @staticmethod
    def _runner_contract_notes(language: str, source_code: str) -> list[str]:
        lower_source = source_code.lower()
        required_markers = {
            "python": ["def solve", "__main__"],
            "java": ["solve(", "class main", "public static void main"],
            "cpp": ["solve(", "int main("],
            "c": ["solve(", "int main("],
        }
        markers = required_markers.get(language, ["solve(", "main("])
        if all(marker in lower_source for marker in markers):
            return [
                "Function-based runner scaffold detected in the reference solution.",
            ]
        direct_runner_markers = {
            "python": [
                ["import sys", "print("],
                ["sys.stdin", "print("],
                ["open(0", "print("],
                ["input(", "print("],
            ],
            "java": [["class main", "public static void main"]],
            "cpp": [["#include", "int main"]],
            "c": [["#include", "int main"]],
        }
        if any(
            all(marker in lower_source for marker in marker_group)
            for marker_group in direct_runner_markers.get(language, [])
        ):
            return [
                "Direct stdin/stdout runner detected in the reference solution.",
            ]
        return [
            (
                "Runner scaffold markers were not fully detected. Validation "
                "still ran against the full source."
            ),
        ]

    def _structured_completion(
        self,
        *,
        schema_name: str,
        schema_model: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
    ) -> Any:
        guarded_system_prompt = build_guarded_system_prompt(
            schema_name=schema_name,
            system_prompt=system_prompt,
        )
        return self._ai_gateway.structured_completion(
            schema_name=schema_name,
            schema_model=schema_model,
            system_prompt=guarded_system_prompt,
            user_prompt=user_prompt,
            task_name=schema_name,
            recruiter_uid=self._current_recruiter_uid,
            prompt_version="v3_structured_contracts",
            workflow_mode=self._current_workflow_mode,
        )

    @staticmethod
    def _append_notes(existing: list[str], *notes: str) -> list[str]:
        merged = [note for note in existing if note]
        merged.extend(note for note in notes if note)
        return merged

    @staticmethod
    def _normalize_tokens(values: list[str]) -> list[str]:
        seen: set[str] = set()
        tokens: list[str] = []
        for value in values:
            token = value.strip().lower()
            if token and token not in seen:
                tokens.append(token)
                seen.add(token)
        return tokens

    @staticmethod
    def _normalize_languages(
        values: list[str],
        preferred_language: str,
        requested_languages: list[str],
    ) -> list[str]:
        base = [
            QuestionAgentUtilsMixin._normalize_solution_language(preferred_language),
        ]
        language_source = requested_languages or values
        for candidate in language_source:
            normalized = QuestionAgentUtilsMixin._normalize_solution_language(candidate)
            if normalized and normalized not in base:
                base.append(normalized)
        return base or ["python"]


__all__ = ["QuestionAgentUtilsMixin"]
