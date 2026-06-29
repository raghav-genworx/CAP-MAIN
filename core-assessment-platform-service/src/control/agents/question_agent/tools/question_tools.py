"""Validation and execution tool routines for the question agent."""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from core.services.execution_adapter_service import ExecutionAdapterService
from schemas.question_bank import (
    SolutionValidationCaseResult,
    SolutionValidationReport,
    SolutionValidationRound,
    TestCase,
)

from ..prompts.adversarial_test_prompt import build_adversarial_test_prompt
from ..prompts.constraint_review_prompt import build_constraint_review_prompt
from ..prompts.question_prompts import (
    ADVERSARIAL_TESTS_PER_ROUND,
    ADVERSARIAL_VALIDATION_ROUNDS,
)
from ..prompts.repair_decision_prompt import build_repair_decision_prompt
from ..prompts.solution_repair_prompt import build_solution_repair_prompt
from ..prompts.testcase_repair_prompt import build_testcase_repair_prompt
from ..states.question_state import (
    HiddenTestOutput,
    QuestionGenerationState,
    RepairDecisionOutput,
    SolutionOutput,
    TestCaseConstraintReviewOutput,
    TestCaseRepairOutput,
)
from ..utils.question_utils import QuestionAgentUtilsMixin

LOGGER = logging.getLogger(__name__)

_SIMPLE_RANGE_RE = re.compile(
    r"(?P<lower>-?\d+(?:\s*\^\s*\d+)?)\s*<=\s*"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*<=\s*"
    r"(?P<upper>-?\d+(?:\s*\^\s*\d+)?)",
)
_INT_RE = re.compile(r"-?\d+")


class QuestionAgentToolsMixin(QuestionAgentUtilsMixin):
    """Execution validation, repair, and testcase helper routines."""

    _execution_adapter: ExecutionAdapterService

    def _run_adversarial_solution_loop(
        self,
        state: QuestionGenerationState,
    ) -> dict[str, Any]:
        source_code = self._sanitize_reference_solution(
            state.get("reference_solution", ""),
        )
        hidden_tests = self._complete_test_cases(
            state.get("hidden_test_cases", []),
        )
        sample_tests = self._complete_test_cases(
            state.get("sample_test_cases", []),
        )
        language = self._normalize_solution_language(
            state.get("reference_language", "python"),
        )
        rounds: list[SolutionValidationRound] = []

        if not source_code or (not sample_tests and not hidden_tests):
            report = self._validate_reference_solution(
                {
                    **state,
                    "reference_solution": source_code,
                    "hidden_test_cases": hidden_tests,
                    "sample_test_cases": sample_tests,
                }
            )
            return {
                "reference_solution": source_code,
                "sample_test_cases": sample_tests,
                "hidden_test_cases": hidden_tests,
                "solution_validation": report,
            }

        for round_number in range(1, ADVERSARIAL_VALIDATION_ROUNDS + 1):
            challenger_tests = self._generate_adversarial_test_cases(
                state=state,
                source_code=source_code,
                existing_sample_tests=sample_tests,
                existing_hidden_tests=hidden_tests,
                round_number=round_number,
            )
            hidden_tests = self._merge_unique_test_cases(
                hidden_tests,
                challenger_tests,
            )
            hidden_tests = self._cap_hidden_tests_for_generation_settings(
                state,
                hidden_tests,
                recently_added_count=len(challenger_tests),
            )
            validation_report = self._validate_source_against_tests(
                language=language,
                source_code=source_code,
                sample_tests=sample_tests,
                hidden_tests=hidden_tests,
                rounds=[],
                time_limit_seconds=state.get("execution_time_limit_seconds"),
                memory_limit_kb=(state.get("memory_limit_mb", 256) * 1024),
            )
            round_status: SolutionValidationRound = SolutionValidationRound(
                round_number=round_number,
                status="passed" if validation_report.failed_count == 0 else "failed",
                summary=validation_report.summary,
                challenger_summary=self._challenger_summary(
                    round_number,
                    challenger_tests,
                ),
                added_hidden_test_cases=challenger_tests,
                passed_count=validation_report.passed_count,
                failed_count=validation_report.failed_count,
                results=validation_report.results,
            )

            if validation_report.failed_count > 0:
                if self._failures_look_like_expected_output_mismatch(
                    validation_report,
                ):
                    repair_decision = RepairDecisionOutput(
                        repair_target="testcase",
                        rationale=(
                            "Execution produced actual output without compile or "
                            "runtime failure, so the loop is repairing expected "
                            "testcase outputs first."
                        ),
                    )
                else:
                    repair_decision = self._decide_repair_target(
                        state=state,
                        source_code=source_code,
                        validation_report=validation_report,
                        sample_tests=sample_tests,
                        hidden_tests=hidden_tests,
                        round_number=round_number,
                    )
                repair_target = repair_decision.repair_target
                repair_summary = repair_decision.rationale
                if repair_target == "testcase":
                    sample_tests, hidden_tests = self._repair_failed_test_cases(
                        state=state,
                        source_code=source_code,
                        validation_report=validation_report,
                        sample_tests=sample_tests,
                        hidden_tests=hidden_tests,
                        round_number=round_number,
                    )
                else:
                    repaired_solution = self._repair_reference_solution(
                        state=state,
                        source_code=source_code,
                        validation_report=validation_report,
                        sample_tests=sample_tests,
                        hidden_tests=hidden_tests,
                        round_number=round_number,
                    )
                    source_code = repaired_solution
                repaired_report = self._validate_source_against_tests(
                    language=language,
                    source_code=source_code,
                    sample_tests=sample_tests,
                    hidden_tests=hidden_tests,
                    rounds=[],
                    time_limit_seconds=state.get("execution_time_limit_seconds"),
                    memory_limit_kb=(state.get("memory_limit_mb", 256) * 1024),
                )
                round_status = round_status.model_copy(
                    update={
                        "status": (
                            (
                                "testcase_repaired"
                                if repair_target == "testcase"
                                else "solution_repaired"
                            )
                            if repaired_report.failed_count == 0
                            else "failed"
                        ),
                        "summary": repaired_report.summary,
                        "repair_summary": repair_summary,
                        "repair_target": repair_target,
                        "decision_summary": repair_decision.rationale,
                        "passed_count": repaired_report.passed_count,
                        "failed_count": repaired_report.failed_count,
                        "results": repaired_report.results,
                    }
                )
                rounds.append(round_status)
                if repaired_report.failed_count > 0:
                    final_report = repaired_report.model_copy(
                        update={"rounds": rounds},
                    )
                    return {
                        "reference_solution": source_code,
                        "sample_test_cases": sample_tests,
                        "hidden_test_cases": hidden_tests,
                        "solution_validation": final_report,
                    }
                continue

            rounds.append(round_status)

        final_report = self._validate_source_against_tests(
            language=language,
            source_code=source_code,
            sample_tests=sample_tests,
            hidden_tests=hidden_tests,
            rounds=rounds,
            time_limit_seconds=state.get("execution_time_limit_seconds"),
            memory_limit_kb=(state.get("memory_limit_mb", 256) * 1024),
        )
        return {
            "reference_solution": source_code,
            "sample_test_cases": sample_tests,
            "hidden_test_cases": hidden_tests,
            "solution_validation": final_report,
        }

    def _generate_adversarial_test_cases(
        self,
        *,
        state: QuestionGenerationState,
        source_code: str,
        existing_sample_tests: list[TestCase],
        existing_hidden_tests: list[TestCase],
        round_number: int,
    ) -> list[TestCase]:
        try:
            system_prompt, user_prompt = build_adversarial_test_prompt(
                state,
                source_code=source_code,
                existing_sample_cases=self._prompt_cases(existing_sample_tests),
                existing_hidden_cases=self._prompt_cases(existing_hidden_tests),
                round_number=round_number,
            )
            model = self._structured_completion(
                schema_name=f"adversarial_tests_round_{round_number}",
                schema_model=HiddenTestOutput,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as exc:  # pragma: no cover - network/model dependent
            LOGGER.warning(
                "Adversarial test generation failed for round %s: %s",
                round_number,
                exc,
            )
            return []

        reviewed_cases = self._validate_test_cases_against_constraints(
            state=state,
            test_cases=[
                case.model_copy(update={"is_sample": False})
                for case in self._complete_test_cases(model.hidden_test_cases)
            ],
            bucket=f"adversarial round {round_number}",
        )
        return reviewed_cases[:ADVERSARIAL_TESTS_PER_ROUND]

    def _decide_repair_target(
        self,
        *,
        state: QuestionGenerationState,
        source_code: str,
        validation_report: SolutionValidationReport,
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
        round_number: int,
    ) -> RepairDecisionOutput:
        failing_results = [
            result.model_dump()
            for result in validation_report.results
            if not result.passed
        ]
        try:
            system_prompt, user_prompt = build_repair_decision_prompt(
                state,
                source_code=source_code,
                sample_cases=self._prompt_cases(sample_tests),
                hidden_cases=self._prompt_cases(hidden_tests),
                failing_results=failing_results,
                round_number=round_number,
            )
            decision = self._structured_completion(
                schema_name=f"repair_decision_round_{round_number}",
                schema_model=RepairDecisionOutput,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            return RepairDecisionOutput.model_validate(decision)
        except Exception as exc:  # pragma: no cover - network/model dependent
            LOGGER.warning("Repair decision failed for round %s: %s", round_number, exc)
            return RepairDecisionOutput(
                repair_target="solution",
                rationale="Decision agent failed; defaulting to solution repair.",
            )

    def _repair_failed_test_cases(
        self,
        *,
        state: QuestionGenerationState,
        source_code: str,
        validation_report: SolutionValidationReport,
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
        round_number: int,
    ) -> tuple[list[TestCase], list[TestCase]]:
        failing_sample_indexes = {
            result.index
            for result in validation_report.results
            if result.bucket == "sample" and not result.passed
        }
        failing_hidden_indexes = {
            result.index
            for result in validation_report.results
            if result.bucket == "hidden" and not result.passed
        }
        preserved_sample_tests = [
            test_case
            for index, test_case in enumerate(sample_tests, start=1)
            if index not in failing_sample_indexes
        ]
        preserved_hidden_tests = [
            test_case
            for index, test_case in enumerate(hidden_tests, start=1)
            if index not in failing_hidden_indexes
        ]
        failing_results = [
            result.model_dump()
            for result in validation_report.results
            if not result.passed
        ]
        try:
            system_prompt, user_prompt = build_testcase_repair_prompt(
                state,
                source_code=source_code,
                preserved_sample_cases=self._prompt_cases(preserved_sample_tests),
                preserved_hidden_cases=self._prompt_cases(preserved_hidden_tests),
                failing_sample_indexes=sorted(failing_sample_indexes),
                failing_hidden_indexes=sorted(failing_hidden_indexes),
                failing_results=failing_results,
                round_number=round_number,
            )
            model = self._structured_completion(
                schema_name=f"testcase_repair_round_{round_number}",
                schema_model=TestCaseRepairOutput,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as exc:  # pragma: no cover - network/model dependent
            LOGGER.warning("Testcase repair failed for round %s: %s", round_number, exc)
            return sample_tests, hidden_tests

        repaired_sample_cases = [
            case.model_copy(update={"is_sample": True})
            for case in self._complete_test_cases(model.sample_test_cases)
        ]
        repaired_hidden_cases = [
            case.model_copy(update={"is_sample": False})
            for case in self._complete_test_cases(model.hidden_test_cases)
        ]
        repaired_sample_cases = self._preserve_repaired_testcase_inputs(
            sample_tests,
            failing_sample_indexes,
            repaired_sample_cases,
            is_sample=True,
        )
        repaired_hidden_cases = self._preserve_repaired_testcase_inputs(
            hidden_tests,
            failing_hidden_indexes,
            repaired_hidden_cases,
            is_sample=False,
        )
        repaired_sample_cases = self._validate_test_cases_against_constraints(
            state=state,
            test_cases=repaired_sample_cases,
            bucket=f"sample testcase repair round {round_number}",
        )
        repaired_hidden_cases = self._validate_test_cases_against_constraints(
            state=state,
            test_cases=repaired_hidden_cases,
            bucket=f"hidden testcase repair round {round_number}",
        )
        return (
            self._replace_failed_test_cases(
                sample_tests,
                failing_sample_indexes,
                repaired_sample_cases,
            ),
            self._replace_failed_test_cases(
                hidden_tests,
                failing_hidden_indexes,
                repaired_hidden_cases,
            ),
        )

    def _repair_reference_solution(
        self,
        *,
        state: QuestionGenerationState,
        source_code: str,
        validation_report: SolutionValidationReport,
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
        round_number: int,
    ) -> str:
        language = state.get("reference_language", "python")
        failing_results = [
            result.model_dump()
            for result in validation_report.results
            if not result.passed
        ]
        try:
            system_prompt, user_prompt = build_solution_repair_prompt(
                state,
                source_code=source_code,
                sample_cases=self._prompt_cases(sample_tests),
                hidden_cases=self._prompt_cases(hidden_tests),
                failing_results=failing_results,
                round_number=round_number,
                language=language,
                strict_contract_guidance=self._strict_solution_contract_guidance(
                    language,
                ),
                language_contract_guidance=self._solution_contract_guidance(language),
            )
            model = self._structured_completion(
                schema_name=f"solution_repair_round_{round_number}",
                schema_model=SolutionOutput,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as exc:  # pragma: no cover - network/model dependent
            LOGGER.warning(
                "Solution repair failed for round %s: %s",
                round_number,
                exc,
            )
            return source_code

        repaired = self._sanitize_reference_solution(model.reference_solution)
        if self._reference_solution_contract_error(repaired, language):
            return source_code
        return repaired or source_code

    @staticmethod
    def _failures_look_like_expected_output_mismatch(
        validation_report: SolutionValidationReport,
    ) -> bool:
        failing_results = [
            result for result in validation_report.results if not result.passed
        ]
        if not failing_results:
            return False

        return all(
            QuestionAgentToolsMixin._is_expected_output_repair_candidate(result)
            for result in failing_results
        )

    @staticmethod
    def _is_expected_output_repair_candidate(
        result: SolutionValidationCaseResult,
    ) -> bool:
        """Return whether execution produced usable output for semantic review."""

        execution_failure_markers = (
            "compile",
            "runtime",
            "time_limit",
            "memory",
            "error",
            "exception",
        )
        status = result.status.lower()
        diagnostic = " ".join(
            [
                result.stderr,
                result.compile_output,
                result.message,
                status,
            ]
        ).lower()
        return bool(result.actual_output.strip()) and not any(
            marker in diagnostic for marker in execution_failure_markers
        )

    @staticmethod
    def _preserve_repaired_testcase_inputs(
        existing: list[TestCase],
        failed_indexes: set[int],
        replacements: list[TestCase],
        *,
        is_sample: bool,
    ) -> list[TestCase]:
        """Accept repaired outputs while retaining each existing testcase input."""

        repaired: list[TestCase] = []
        for index, replacement in zip(
            sorted(failed_indexes),
            replacements,
            strict=False,
        ):
            if index < 1 or index > len(existing):
                continue
            original = existing[index - 1]
            repaired.append(
                TestCase(
                    input=original.input,
                    expected_output=replacement.expected_output,
                    is_sample=is_sample,
                    explanation=replacement.explanation or original.explanation,
                )
            )
        return repaired

    @staticmethod
    def _merge_unique_test_cases(
        existing: list[TestCase],
        candidates: list[TestCase],
    ) -> list[TestCase]:
        merged = list(existing)
        seen = {(case.input.strip(), case.expected_output.strip()) for case in existing}
        for candidate in candidates:
            key = (candidate.input.strip(), candidate.expected_output.strip())
            if key[0] and key[1] and key not in seen:
                merged.append(candidate)
                seen.add(key)
        return merged

    @staticmethod
    def _cap_hidden_tests_for_generation_settings(
        state: QuestionGenerationState,
        hidden_tests: list[TestCase],
        *,
        recently_added_count: int,
    ) -> list[TestCase]:
        target_count = max(1, state["generation_settings"].hidden_test_case_count)
        if len(hidden_tests) <= target_count:
            return hidden_tests
        if recently_added_count <= 0:
            return hidden_tests[:target_count]

        kept_recent_count = min(recently_added_count, target_count)
        kept_base_count = target_count - kept_recent_count
        return hidden_tests[:kept_base_count] + hidden_tests[-kept_recent_count:]

    @staticmethod
    def _replace_failed_test_cases(
        existing: list[TestCase],
        failed_indexes: set[int],
        replacements: list[TestCase],
    ) -> list[TestCase]:
        if not failed_indexes:
            return existing

        replacement_queue = list(replacements)
        repaired: list[TestCase] = []
        for index, test_case in enumerate(existing, start=1):
            if index in failed_indexes and replacement_queue:
                repaired.append(replacement_queue.pop(0))
            else:
                repaired.append(test_case)
        repaired.extend(replacement_queue)
        return repaired

    @staticmethod
    def _parse_constraint_number(raw_value: str) -> int | None:
        normalized = raw_value.replace(" ", "")
        if "^" in normalized:
            base, exponent = normalized.split("^", 1)
            if base.lstrip("-").isdigit() and exponent.isdigit():
                return int(pow(int(base), int(exponent)))
            return None
        if normalized.lstrip("-").isdigit():
            return int(normalized)
        return None

    def _script_filter_test_cases_against_constraints(
        self,
        *,
        constraints: str,
        test_cases: list[TestCase],
        bucket: str,
    ) -> list[TestCase]:
        """Conservative deterministic bound check for simple if/else-style inputs."""

        ranges: list[tuple[str, int, int]] = []
        for match in _SIMPLE_RANGE_RE.finditer(constraints):
            lower = self._parse_constraint_number(match.group("lower"))
            upper = self._parse_constraint_number(match.group("upper"))
            if lower is None or upper is None:
                continue
            ranges.append((match.group("name"), min(lower, upper), max(lower, upper)))

        if len(ranges) != 1:
            return test_cases

        variable_name, lower_bound, upper_bound = ranges[0]
        accepted: list[TestCase] = []
        for index, test_case in enumerate(test_cases, start=1):
            values = [int(value) for value in _INT_RE.findall(test_case.input)]
            if len(values) != 1:
                accepted.append(test_case)
                continue
            value = values[0]
            if lower_bound <= value <= upper_bound:
                accepted.append(test_case)
                continue
            LOGGER.info(
                (
                    "Script constraint check rejected %s testcase %s: %s=%s "
                    "outside [%s, %s]"
                ),
                bucket,
                index,
                variable_name,
                value,
                lower_bound,
                upper_bound,
            )
        return accepted

    def _validate_test_cases_against_constraints(
        self,
        *,
        state: QuestionGenerationState,
        test_cases: list[TestCase],
        bucket: str,
    ) -> list[TestCase]:
        complete_cases = self._complete_test_cases(test_cases)
        constraints = state.get("constraints", "").strip()
        if not complete_cases or not constraints:
            return complete_cases
        complete_cases = self._script_filter_test_cases_against_constraints(
            constraints=constraints,
            test_cases=complete_cases,
            bucket=bucket,
        )
        if not complete_cases:
            LOGGER.warning(
                (
                    "Script constraint check rejected all %s tests; preserving "
                    "generated cases for manual review."
                ),
                bucket,
            )
            return self._complete_test_cases(test_cases)

        try:
            system_prompt, user_prompt = build_constraint_review_prompt(
                state,
                bucket=bucket,
                constraints=constraints,
                test_cases=self._prompt_cases(complete_cases),
            )
            review = self._structured_completion(
                schema_name=f"{bucket.replace(' ', '_')}_constraint_review",
                schema_model=TestCaseConstraintReviewOutput,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except Exception as exc:  # pragma: no cover - network/model dependent
            LOGGER.warning("Constraint review failed for %s tests: %s", bucket, exc)
            return complete_cases

        valid_indexes = {
            index for index in review.valid_indexes if 1 <= index <= len(complete_cases)
        }
        if not valid_indexes and complete_cases:
            LOGGER.warning(
                (
                    "Constraint review rejected all %s tests; preserving "
                    "generated cases for manual review."
                ),
                bucket,
            )
            return complete_cases

        rejected_count = len(complete_cases) - len(valid_indexes)
        if rejected_count:
            LOGGER.info(
                "Constraint review rejected %s %s testcase(s): %s",
                rejected_count,
                bucket,
                review.invalid_notes,
            )
        return [
            case
            for index, case in enumerate(complete_cases, start=1)
            if index in valid_indexes
        ]

    @staticmethod
    def _challenger_summary(
        round_number: int,
        challenger_tests: list[TestCase],
    ) -> str:
        if not challenger_tests:
            return (
                f"Round {round_number}: challenger reused the accumulated tests "
                "because no new valid adversarial case was produced."
            )
        return (
            f"Round {round_number}: challenger added "
            f"{len(challenger_tests)} adversarial hidden test"
            f"{'' if len(challenger_tests) == 1 else 's'}."
        )

    def _validate_reference_solution(
        self,
        state: QuestionGenerationState,
    ) -> SolutionValidationReport:
        source_code = self._sanitize_reference_solution(
            state.get("reference_solution", ""),
        )
        if not source_code:
            return SolutionValidationReport(
                status="skipped",
                summary=(
                    "Execution validation skipped because the reference solution "
                    "is empty."
                ),
                runner_notes=["Generate or enter a runnable reference solution first."],
            )

        complete_sample_tests = self._complete_test_cases(
            state.get("sample_test_cases", []),
        )
        complete_hidden_tests = self._complete_test_cases(
            state.get("hidden_test_cases", []),
        )
        if not complete_sample_tests and not complete_hidden_tests:
            return SolutionValidationReport(
                status="skipped",
                summary=(
                    "Execution validation skipped because there are no complete "
                    "test cases yet."
                ),
                runner_notes=[
                    "Add sample or hidden test cases before validating the solution.",
                ],
            )

        language = self._normalize_solution_language(
            state.get("reference_language", "python"),
        )
        contract_error = self._reference_solution_contract_error(source_code, language)
        if contract_error:
            return self._source_contract_failure_report(
                language=language,
                sample_tests=complete_sample_tests,
                hidden_tests=complete_hidden_tests,
                rounds=[],
                contract_error=contract_error,
            )
        return self._validate_source_against_tests(
            language=language,
            source_code=source_code,
            sample_tests=complete_sample_tests,
            hidden_tests=complete_hidden_tests,
            rounds=[],
            time_limit_seconds=state.get("execution_time_limit_seconds"),
            memory_limit_kb=(state.get("memory_limit_mb", 256) * 1024),
        )

    def _validate_source_against_tests(
        self,
        *,
        language: str,
        source_code: str,
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
        rounds: list[SolutionValidationRound],
        time_limit_seconds: float | None = None,
        memory_limit_kb: int | None = None,
    ) -> SolutionValidationReport:
        contract_error = self._reference_solution_contract_error(source_code, language)
        if contract_error:
            return self._source_contract_failure_report(
                language=language,
                sample_tests=sample_tests,
                hidden_tests=hidden_tests,
                rounds=rounds,
                contract_error=contract_error,
            )
        runner_notes = self._runner_contract_notes(language, source_code)
        results: list[SolutionValidationCaseResult] = []
        if sample_tests:
            sample_results, _, _ = self._execution_adapter.execute_batch(
                source_code=source_code,
                language=language,
                test_cases=sample_tests,
                run_type="sample_run",
                time_limit_seconds=time_limit_seconds,
                memory_limit_kb=memory_limit_kb,
            )
            for index, result in enumerate(sample_results, start=1):
                results.append(
                    SolutionValidationCaseResult(
                        bucket="sample",
                        index=index,
                        passed=result.passed,
                        status=result.status,
                        stdin=result.input,
                        expected_output=result.expected_output,
                        actual_output=result.actual_output,
                        stderr=result.stderr,
                        compile_output=result.compile_output,
                        message=result.message,
                        token=result.token,
                        execution_time=result.execution_time,
                        memory_kb=result.memory_kb,
                    )
                )
        if hidden_tests:
            hidden_results, _, _ = self._execution_adapter.execute_batch(
                source_code=source_code,
                language=language,
                test_cases=hidden_tests,
                run_type="final_hidden",
                time_limit_seconds=time_limit_seconds,
                memory_limit_kb=memory_limit_kb,
            )
            for index, result in enumerate(hidden_results, start=1):
                results.append(
                    SolutionValidationCaseResult(
                        bucket="hidden",
                        index=index,
                        passed=result.passed,
                        status=result.status,
                        stdin=result.input,
                        expected_output=result.expected_output,
                        actual_output=result.actual_output,
                        stderr=result.stderr,
                        compile_output=result.compile_output,
                        message=result.message,
                        token=result.token,
                        execution_time=result.execution_time,
                        memory_kb=result.memory_kb,
                    )
                )

        passed_count = sum(1 for item in results if item.passed)
        failed_count = len(results) - passed_count
        status: Literal["passed", "failed"] = (
            "passed" if failed_count == 0 else "failed"
        )
        summary = (
            f"Reference solution passed {passed_count}/{len(results)} execution checks."
            if status == "passed"
            else (
                f"Reference solution failed {failed_count} of {len(results)} "
                "execution checks."
            )
        )
        return SolutionValidationReport(
            status=status,
            summary=summary,
            passed_count=passed_count,
            failed_count=failed_count,
            sample_count=len(sample_tests),
            hidden_count=len(hidden_tests),
            runner_notes=runner_notes,
            results=results,
            rounds=rounds,
        )


__all__ = ["QuestionAgentToolsMixin"]
