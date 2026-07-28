"""Validation and execution tool routines for the question agent."""

from __future__ import annotations

import ast
import json
import logging
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Literal

from core.exceptions.assessment import ExecutionAdapterError
from core.services.execution.ports import ExecutionPort
from core.services.question_bank.output_validation import (
    apply_answer_validation,
    default_checker_explanation,
    normalize_answer_validation_mode,
)
from schemas.question_bank import (
    AnswerValidationMode,
    SolutionValidationCaseResult,
    SolutionValidationReport,
    SolutionValidationRound,
    TestCase,
    ValidationStatus,
)

from ..prompts.adversarial_test_prompt import build_adversarial_test_prompt
from ..prompts.constraint_replacement_prompt import build_constraint_replacement_prompt
from ..prompts.constraint_review_prompt import build_constraint_review_prompt
from ..prompts.constraint_script_prompt import build_constraint_script_prompt
from ..prompts.question_prompts import (
    ADVERSARIAL_TESTS_PER_ROUND,
    ADVERSARIAL_VALIDATION_ROUNDS,
)
from ..prompts.repair_decision_prompt import build_repair_decision_prompt
from ..prompts.solution_repair_prompt import build_solution_repair_prompt
from ..prompts.testcase_repair_prompt import build_testcase_repair_prompt
from ..states.question_state import (
    ConstraintValidationScriptOutput,
    HiddenTestOutput,
    QuestionGenerationState,
    RepairDecisionOutput,
    SolutionOutput,
    TestCaseConstraintReviewOutput,
    TestCaseRepairOutput,
)
from ..utils.question_utils import QuestionAgentUtilsMixin

LOGGER = logging.getLogger(__name__)
CONSTRAINT_SCRIPT_REPLACEMENT_ROUNDS = 2
CONSTRAINT_SCRIPT_TIMEOUT_SECONDS = 2.0


@dataclass
class _ValidationProgressContext:
    callback: Callable[[dict[str, Any]], None]
    validation_pass: int = 0


_VALIDATION_PROGRESS_CONTEXT: ContextVar[_ValidationProgressContext | None] = (
    ContextVar("question_validation_progress", default=None)
)


@contextmanager
def validation_progress_events(
    callback: Callable[[dict[str, Any]], None],
) -> Iterator[None]:
    """Publish individual execution results for a streamed validation node."""

    token = _VALIDATION_PROGRESS_CONTEXT.set(
        _ValidationProgressContext(callback=callback),
    )
    try:
        yield
    finally:
        _VALIDATION_PROGRESS_CONTEXT.reset(token)


_SIMPLE_RANGE_RE = re.compile(
    r"(?P<lower>-?\d+(?:\s*\^\s*\d+)?)\s*<=\s*"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*<=\s*"
    r"(?P<upper>-?\d+(?:\s*\^\s*\d+)?)",
)
_INT_RE = re.compile(r"-?\d+")


class QuestionAgentToolsMixin(QuestionAgentUtilsMixin):
    """Execution validation, repair, and testcase helper routines."""

    _execution_adapter: ExecutionPort

    @staticmethod
    def _answer_validation_kwargs(
        state: QuestionGenerationState,
    ) -> dict[str, str]:
        answer_mode = normalize_answer_validation_mode(
            state.get("answer_validation_mode", AnswerValidationMode.EXACT.value),
        )
        return {
            "answer_validation_mode": answer_mode,
            "output_checker": state.get("output_checker", "") or "",
            "output_checker_explanation": (
                state.get("output_checker_explanation", "") or ""
            ),
        }

    def _generate_constraint_validation_script(
        self,
        state: QuestionGenerationState,
    ) -> str:
        """Generate and contract-check a Python testcase constraint validator."""

        system_prompt, user_prompt = build_constraint_script_prompt(state)
        model = self._structured_completion(
            schema_name="constraint_validation_script",
            schema_model=ConstraintValidationScriptOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        script = self._sanitize_reference_solution(model.python_script)
        contract_error = self._constraint_script_contract_error(script)
        if contract_error:
            raise ValueError(contract_error)
        return script

    def _repair_constraint_invalid_test_cases(
        self,
        *,
        state: QuestionGenerationState,
        script: str,
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
        sample_rejections: list[dict[str, Any]],
        hidden_rejections: list[dict[str, Any]],
    ) -> tuple[list[TestCase], list[TestCase], list[str], int]:
        """Generate replacements and accept only rows that pass the script."""

        warnings: list[str] = []
        sample_indexes = {int(item["index"]) for item in sample_rejections}
        hidden_indexes = {int(item["index"]) for item in hidden_rejections}
        valid_sample_tests = [
            test_case
            for index, test_case in enumerate(sample_tests, start=1)
            if index not in sample_indexes
        ]
        valid_hidden_tests = [
            test_case
            for index, test_case in enumerate(hidden_tests, start=1)
            if index not in hidden_indexes
        ]
        sample_replacements: list[TestCase] = []
        hidden_replacements: list[TestCase] = []
        seen_inputs = {
            test_case.input.strip()
            for test_case in [*valid_sample_tests, *valid_hidden_tests]
            if test_case.input.strip()
        }
        all_rejections = [*sample_rejections, *hidden_rejections]

        for attempt in range(1, CONSTRAINT_SCRIPT_REPLACEMENT_ROUNDS + 1):
            if len(sample_replacements) >= len(sample_indexes) and len(
                hidden_replacements
            ) >= len(hidden_indexes):
                break
            model = self._generate_constraint_replacement_candidates(
                state=state,
                invalid_sample_cases=sample_rejections,
                invalid_hidden_cases=hidden_rejections,
                valid_sample_cases=self._prompt_cases(valid_sample_tests),
                valid_hidden_cases=self._prompt_cases(valid_hidden_tests),
                script_rejections=all_rejections,
                attempt=attempt,
            )
            for candidate in self._complete_test_cases(model.sample_test_cases):
                if len(sample_replacements) >= len(sample_indexes):
                    break
                accepted = self._accept_constraint_replacement(
                    script=script,
                    candidate=candidate.model_copy(update={"is_sample": True}),
                    bucket="sample",
                    seen_inputs=seen_inputs,
                )
                if accepted:
                    sample_replacements.append(accepted)
            for candidate in self._complete_test_cases(model.hidden_test_cases):
                if len(hidden_replacements) >= len(hidden_indexes):
                    break
                accepted = self._accept_constraint_replacement(
                    script=script,
                    candidate=candidate.model_copy(update={"is_sample": False}),
                    bucket="hidden",
                    seen_inputs=seen_inputs,
                )
                if accepted:
                    hidden_replacements.append(accepted)

        repaired_sample_tests = self._replace_failed_test_cases(
            sample_tests,
            sample_indexes,
            sample_replacements,
        )
        repaired_hidden_tests = self._replace_failed_test_cases(
            hidden_tests,
            hidden_indexes,
            hidden_replacements,
        )
        replaced_count = min(len(sample_indexes), len(sample_replacements)) + min(
            len(hidden_indexes),
            len(hidden_replacements),
        )
        missing_count = len(sample_indexes) + len(hidden_indexes) - replaced_count
        if missing_count:
            warnings.append(
                (
                    "Constraint script rejected testcase inputs, but AI generated "
                    f"only {replaced_count} valid replacement(s); {missing_count} "
                    "row(s) still need recruiter review."
                ),
            )
        return repaired_sample_tests, repaired_hidden_tests, warnings, replaced_count

    def _generate_constraint_replacement_candidates(
        self,
        *,
        state: QuestionGenerationState,
        invalid_sample_cases: list[dict[str, Any]],
        invalid_hidden_cases: list[dict[str, Any]],
        valid_sample_cases: list[dict[str, Any]],
        valid_hidden_cases: list[dict[str, Any]],
        script_rejections: list[dict[str, Any]],
        attempt: int,
    ) -> TestCaseRepairOutput:
        system_prompt, user_prompt = build_constraint_replacement_prompt(
            state,
            invalid_sample_cases=invalid_sample_cases,
            invalid_hidden_cases=invalid_hidden_cases,
            valid_sample_cases=valid_sample_cases,
            valid_hidden_cases=valid_hidden_cases,
            script_rejections=script_rejections,
            attempt=attempt,
        )
        model = self._structured_completion(
            schema_name=f"constraint_replacement_round_{attempt}",
            schema_model=TestCaseRepairOutput,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
        return TestCaseRepairOutput.model_validate(model)

    def _accept_constraint_replacement(
        self,
        *,
        script: str,
        candidate: TestCase,
        bucket: Literal["sample", "hidden"],
        seen_inputs: set[str],
    ) -> TestCase | None:
        input_key = candidate.input.strip()
        if not input_key or input_key in seen_inputs:
            return None
        result = self._run_constraint_script_for_case(
            script=script,
            test_case=candidate,
            bucket=bucket,
            index=0,
        )
        if not result["valid"]:
            return None
        seen_inputs.add(input_key)
        return candidate

    def _run_constraint_script_for_cases(
        self,
        *,
        script: str,
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for index, test_case in enumerate(sample_tests, start=1):
            results.append(
                self._run_constraint_script_for_case(
                    script=script,
                    test_case=test_case,
                    bucket="sample",
                    index=index,
                ),
            )
        for index, test_case in enumerate(hidden_tests, start=1):
            results.append(
                self._run_constraint_script_for_case(
                    script=script,
                    test_case=test_case,
                    bucket="hidden",
                    index=index,
                ),
            )
        return results

    def _run_constraint_script_for_case(
        self,
        *,
        script: str,
        test_case: TestCase,
        bucket: Literal["sample", "hidden"],
        index: int,
    ) -> dict[str, Any]:
        payload = json.dumps({"stdin": test_case.input, "bucket": bucket})
        runner = (
            f"{script}\n\n"
            "import json as __constraint_json\n"
            f"__payload = __constraint_json.loads({payload!r})\n"
            "try:\n"
            "    __result = validate_testcase(\n"
            "        __payload['stdin'],\n"
            "        __payload['bucket'],\n"
            "    )\n"
            "    __valid = bool(__result[0])\n"
            "    __reason = str(__result[1] if len(__result) > 1 else '')\n"
            "except BaseException as __exc:\n"
            "    __valid = False\n"
            "    __reason = f'validator error: {type(__exc).__name__}'\n"
            "print(__constraint_json.dumps({'valid': __valid, 'reason': __reason}))\n"
        )
        try:
            completed = subprocess.run(
                [sys.executable, "-I", "-c", runner],
                capture_output=True,
                check=False,
                text=True,
                timeout=CONSTRAINT_SCRIPT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return {
                "bucket": bucket,
                "index": index,
                "testcase": test_case.model_dump(mode="json"),
                "valid": False,
                "reason": "constraint validator timed out",
            }
        if completed.returncode != 0:
            return {
                "bucket": bucket,
                "index": index,
                "testcase": test_case.model_dump(mode="json"),
                "valid": False,
                "reason": "constraint validator failed",
            }
        try:
            parsed = json.loads(completed.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            parsed = {"valid": False, "reason": "constraint validator gave no result"}
        return {
            "bucket": bucket,
            "index": index,
            "testcase": test_case.model_dump(mode="json"),
            "valid": bool(parsed.get("valid")),
            "reason": str(parsed.get("reason") or ""),
        }

    @staticmethod
    def _constraint_script_contract_error(script: str) -> str:
        if not script.strip():
            return "Constraint validation script is empty."
        try:
            tree = ast.parse(script)
        except SyntaxError as exc:
            return f"Constraint validation script has invalid syntax: {exc.msg}."

        function_names = {
            node.name for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        if "validate_testcase" not in function_names:
            return "Constraint validation script must define validate_testcase."
        disallowed_top_level = [
            node for node in tree.body if not isinstance(node, ast.FunctionDef)
        ]
        if disallowed_top_level:
            return "Constraint validation script must not perform top-level work."

        allowed_call_names = {
            *function_names,
            "abs",
            "all",
            "any",
            "bool",
            "dict",
            "enumerate",
            "float",
            "int",
            "len",
            "list",
            "map",
            "max",
            "min",
            "range",
            "set",
            "sorted",
            "str",
            "sum",
            "tuple",
            "zip",
        }
        allowed_method_names = {
            "append",
            "count",
            "endswith",
            "extend",
            "get",
            "isdigit",
            "join",
            "lower",
            "lstrip",
            "replace",
            "rstrip",
            "split",
            "startswith",
            "strip",
            "upper",
        }
        forbidden_nodes = (
            ast.AsyncFunctionDef,
            ast.ClassDef,
            ast.Delete,
            ast.Global,
            ast.Import,
            ast.ImportFrom,
            ast.Nonlocal,
            ast.Raise,
            ast.With,
        )
        forbidden_names = {
            "__import__",
            "breakpoint",
            "compile",
            "eval",
            "exec",
            "globals",
            "input",
            "locals",
            "open",
            "print",
        }
        for node in ast.walk(tree):
            if isinstance(node, forbidden_nodes):
                return (
                    "Constraint validation script contains unsupported Python "
                    f"syntax: {type(node).__name__}."
                )
            if isinstance(node, ast.Name) and node.id in forbidden_names:
                return f"Constraint validation script uses a forbidden name: {node.id}."
            if isinstance(node, ast.Attribute) and (
                node.attr.startswith("__") or node.attr not in allowed_method_names
            ):
                return (
                    "Constraint validation script uses an unsupported attribute: "
                    f"{node.attr}."
                )
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id not in allowed_call_names:
                        return (
                            "Constraint validation script calls unsupported "
                            f"function: {node.func.id}."
                        )
                elif isinstance(node.func, ast.Attribute):
                    if node.func.attr not in allowed_method_names:
                        return (
                            "Constraint validation script calls unsupported "
                            f"method: {node.func.attr}."
                        )
                else:
                    return "Constraint validation script has an unsafe call."
        return ""

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

        initial_report = self._validate_source_against_tests(
            language=language,
            source_code=source_code,
            sample_tests=sample_tests,
            hidden_tests=hidden_tests,
            rounds=[],
            time_limit_seconds=state.get("execution_time_limit_seconds"),
            memory_limit_kb=(state.get("memory_limit_mb", 256) * 1024),
            **self._answer_validation_kwargs(state),
        )
        if initial_report.failed_count == 0:
            return {
                "reference_solution": source_code,
                "sample_test_cases": sample_tests,
                "hidden_test_cases": hidden_tests,
                "solution_validation": initial_report,
            }

        validation_report = initial_report
        for round_number in range(1, ADVERSARIAL_VALIDATION_ROUNDS + 1):
            round_status: SolutionValidationRound = SolutionValidationRound(
                round_number=round_number,
                status="passed" if validation_report.failed_count == 0 else "failed",
                summary=validation_report.summary,
                challenger_summary=(
                    "Used the failing sample and hidden cases from the first "
                    "validation pass."
                ),
                added_hidden_test_cases=[],
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
                    failing_sample_indexes, failing_hidden_indexes = (
                        self._failed_result_indexes(validation_report)
                    )
                    sample_tests, hidden_tests = self._repair_failed_test_cases(
                        state=state,
                        source_code=source_code,
                        validation_report=validation_report,
                        sample_tests=sample_tests,
                        hidden_tests=hidden_tests,
                        round_number=round_number,
                    )
                    focused_sample_tests = self._select_tests_by_indexes(
                        sample_tests,
                        failing_sample_indexes,
                    )
                    focused_hidden_tests = self._select_tests_by_indexes(
                        hidden_tests,
                        failing_hidden_indexes,
                    )
                    focused_report = self._validate_source_against_tests(
                        language=language,
                        source_code=source_code,
                        sample_tests=focused_sample_tests,
                        hidden_tests=focused_hidden_tests,
                        rounds=[],
                        time_limit_seconds=state.get("execution_time_limit_seconds"),
                        memory_limit_kb=(state.get("memory_limit_mb", 256) * 1024),
                        **self._answer_validation_kwargs(state),
                    )
                    repaired_report = self._merge_focused_validation_report(
                        validation_report,
                        focused_report,
                        sample_indexes=failing_sample_indexes,
                        hidden_indexes=failing_hidden_indexes,
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
                        **self._answer_validation_kwargs(state),
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
                    validation_report = repaired_report
                    continue
                return {
                    "reference_solution": source_code,
                    "sample_test_cases": sample_tests,
                    "hidden_test_cases": hidden_tests,
                    "solution_validation": repaired_report.model_copy(
                        update={"rounds": rounds},
                    ),
                }

            rounds.append(round_status)
            return {
                "reference_solution": source_code,
                "sample_test_cases": sample_tests,
                "hidden_test_cases": hidden_tests,
                "solution_validation": validation_report.model_copy(
                    update={"rounds": rounds},
                ),
            }

        final_report = self._validate_source_against_tests(
            language=language,
            source_code=source_code,
            sample_tests=sample_tests,
            hidden_tests=hidden_tests,
            rounds=rounds,
            time_limit_seconds=state.get("execution_time_limit_seconds"),
            memory_limit_kb=(state.get("memory_limit_mb", 256) * 1024),
            **self._answer_validation_kwargs(state),
        )
        if final_report.failed_count > 0:
            (
                sample_tests,
                hidden_tests,
                final_report,
                rounds,
            ) = self._run_final_testcase_repair_if_needed(
                state=state,
                source_code=source_code,
                language=language,
                validation_report=final_report,
                sample_tests=sample_tests,
                hidden_tests=hidden_tests,
                rounds=rounds,
                round_number=ADVERSARIAL_VALIDATION_ROUNDS + 1,
            )
        return {
            "reference_solution": source_code,
            "sample_test_cases": sample_tests,
            "hidden_test_cases": hidden_tests,
            "solution_validation": final_report,
        }

    def _run_final_testcase_repair_if_needed(
        self,
        *,
        state: QuestionGenerationState,
        source_code: str,
        language: str,
        validation_report: SolutionValidationReport,
        sample_tests: list[TestCase],
        hidden_tests: list[TestCase],
        rounds: list[SolutionValidationRound],
        round_number: int,
    ) -> tuple[
        list[TestCase],
        list[TestCase],
        SolutionValidationReport,
        list[SolutionValidationRound],
    ]:
        if validation_report.failed_count == 0:
            return sample_tests, hidden_tests, validation_report, rounds
        if not self._failures_look_like_expected_output_mismatch(validation_report):
            return (
                sample_tests,
                hidden_tests,
                validation_report.model_copy(update={"rounds": rounds}),
                rounds,
            )

        final_round_number = min(round_number, ADVERSARIAL_VALIDATION_ROUNDS + 1)
        failing_sample_indexes, failing_hidden_indexes = self._failed_result_indexes(
            validation_report,
        )
        repaired_sample_tests, repaired_hidden_tests = self._repair_failed_test_cases(
            state=state,
            source_code=source_code,
            validation_report=validation_report,
            sample_tests=sample_tests,
            hidden_tests=hidden_tests,
            round_number=final_round_number,
        )
        focused_sample_tests = self._select_tests_by_indexes(
            repaired_sample_tests,
            failing_sample_indexes,
        )
        focused_hidden_tests = self._select_tests_by_indexes(
            repaired_hidden_tests,
            failing_hidden_indexes,
        )
        focused_report = self._validate_source_against_tests(
            language=language,
            source_code=source_code,
            sample_tests=focused_sample_tests,
            hidden_tests=focused_hidden_tests,
            rounds=[],
            time_limit_seconds=state.get("execution_time_limit_seconds"),
            memory_limit_kb=(state.get("memory_limit_mb", 256) * 1024),
            **self._answer_validation_kwargs(state),
        )
        repaired_report = self._merge_focused_validation_report(
            validation_report,
            focused_report,
            sample_indexes=failing_sample_indexes,
            hidden_indexes=failing_hidden_indexes,
        )
        final_round = SolutionValidationRound(
            round_number=final_round_number,
            status=(
                "testcase_repaired" if repaired_report.failed_count == 0 else "failed"
            ),
            summary=repaired_report.summary,
            challenger_summary=(
                "Final testcase refinement after validation still showed "
                "expected-output mismatches."
            ),
            repair_summary=(
                "Recomputed failed testcase expected outputs and validated "
                "the same reference solution again."
            ),
            repair_target="testcase",
            decision_summary=(
                "Program execution produced actual output without compile or "
                "runtime failure, so the final pass refined testcase outputs."
            ),
            passed_count=repaired_report.passed_count,
            failed_count=repaired_report.failed_count,
            results=repaired_report.results,
        )
        next_rounds = [*rounds, final_round]
        return (
            repaired_sample_tests,
            repaired_hidden_tests,
            repaired_report.model_copy(update={"rounds": next_rounds}),
            next_rounds,
        )

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

    @staticmethod
    def _failed_result_indexes(
        validation_report: SolutionValidationReport,
    ) -> tuple[set[int], set[int]]:
        return (
            {
                result.index
                for result in validation_report.results
                if result.bucket == "sample" and not result.passed
            },
            {
                result.index
                for result in validation_report.results
                if result.bucket == "hidden" and not result.passed
            },
        )

    @staticmethod
    def _select_tests_by_indexes(
        test_cases: list[TestCase],
        indexes: set[int],
    ) -> list[TestCase]:
        return [
            test_case
            for index, test_case in enumerate(test_cases, start=1)
            if index in indexes
        ]

    @staticmethod
    def _merge_focused_validation_report(
        previous_report: SolutionValidationReport,
        focused_report: SolutionValidationReport,
        *,
        sample_indexes: set[int],
        hidden_indexes: set[int],
    ) -> SolutionValidationReport:
        sample_index_list = sorted(sample_indexes)
        hidden_index_list = sorted(hidden_indexes)
        merged_results = {
            (result.bucket, result.index): result for result in previous_report.results
        }

        for result in focused_report.results:
            if result.bucket == "sample":
                if result.index < 1 or result.index > len(sample_index_list):
                    continue
                original_index = sample_index_list[result.index - 1]
            else:
                if result.index < 1 or result.index > len(hidden_index_list):
                    continue
                original_index = hidden_index_list[result.index - 1]
            merged_results[(result.bucket, original_index)] = result.model_copy(
                update={"index": original_index},
            )

        ordered_results = [
            merged_results[key]
            for key in sorted(
                merged_results,
                key=lambda item: (0 if item[0] == "sample" else 1, item[1]),
            )
        ]
        passed_count = sum(1 for result in ordered_results if result.passed)
        failed_count = len(ordered_results) - passed_count
        status: Literal["passed", "failed"] = (
            "passed" if failed_count == 0 else "failed"
        )
        summary = (
            f"Reference solution passed {passed_count}/{len(ordered_results)} "
            "execution checks."
            if status == "passed"
            else (
                f"Reference solution failed {failed_count} of "
                f"{len(ordered_results)} execution checks."
            )
        )
        return previous_report.model_copy(
            update={
                "status": status,
                "summary": summary,
                "passed_count": passed_count,
                "failed_count": failed_count,
                "results": ordered_results,
            },
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
            **self._answer_validation_kwargs(state),
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
        answer_validation_mode: str | AnswerValidationMode = AnswerValidationMode.EXACT,
        output_checker: str = "",
        output_checker_explanation: str = "",
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
        normalized_answer_mode = AnswerValidationMode(
            normalize_answer_validation_mode(answer_validation_mode),
        )
        checker_source = output_checker.strip()
        checker_explanation = (
            output_checker_explanation.strip()
            or default_checker_explanation(normalized_answer_mode)
        )
        runner_notes = [
            *self._runner_contract_notes(language, source_code),
            f"Answer validation mode: {normalized_answer_mode.value}.",
            checker_explanation,
        ]
        try:
            results: list[SolutionValidationCaseResult] = []
            progress_context = _VALIDATION_PROGRESS_CONTEXT.get()
            if progress_context is not None:
                progress_context.validation_pass += 1
                validation_pass = progress_context.validation_pass
                total_cases = len(sample_tests) + len(hidden_tests)
                results.extend(
                    self._execute_streamed_validation_cases(
                        progress_context=progress_context,
                        validation_pass=validation_pass,
                        bucket="sample",
                        test_cases=sample_tests,
                        source_code=source_code,
                        language=language,
                        run_type="sample_run",
                        total_cases=total_cases,
                        overall_offset=0,
                        time_limit_seconds=time_limit_seconds,
                        memory_limit_kb=memory_limit_kb,
                        answer_validation_mode=normalized_answer_mode,
                        output_checker=checker_source,
                    )
                )
                results.extend(
                    self._execute_streamed_validation_cases(
                        progress_context=progress_context,
                        validation_pass=validation_pass,
                        bucket="hidden",
                        test_cases=hidden_tests,
                        source_code=source_code,
                        language=language,
                        run_type="final_hidden",
                        total_cases=total_cases,
                        overall_offset=len(sample_tests),
                        time_limit_seconds=time_limit_seconds,
                        memory_limit_kb=memory_limit_kb,
                        answer_validation_mode=normalized_answer_mode,
                        output_checker=checker_source,
                    )
                )
            elif sample_tests:
                sample_results, _, _ = self._execution_adapter.execute_batch(
                    source_code=source_code,
                    language=language,
                    test_cases=sample_tests,
                    run_type="sample_run",
                    time_limit_seconds=time_limit_seconds,
                    memory_limit_kb=memory_limit_kb,
                )
                for index, result in enumerate(sample_results, start=1):
                    scored_result = apply_answer_validation(
                        result,
                        mode=normalized_answer_mode,
                        checker_source=checker_source,
                    )
                    results.append(
                        SolutionValidationCaseResult(
                            bucket="sample",
                            index=index,
                            passed=scored_result.passed,
                            status=scored_result.status,
                            stdin=scored_result.input,
                            expected_output=scored_result.expected_output,
                            actual_output=scored_result.actual_output,
                            stderr=scored_result.stderr,
                            compile_output=scored_result.compile_output,
                            message=scored_result.message,
                            checker_message=scored_result.checker_message,
                            token=scored_result.token,
                            execution_time=scored_result.execution_time,
                            memory_kb=scored_result.memory_kb,
                        )
                    )
            if progress_context is None and hidden_tests:
                hidden_results, _, _ = self._execution_adapter.execute_batch(
                    source_code=source_code,
                    language=language,
                    test_cases=hidden_tests,
                    run_type="final_hidden",
                    time_limit_seconds=time_limit_seconds,
                    memory_limit_kb=memory_limit_kb,
                )
                for index, result in enumerate(hidden_results, start=1):
                    scored_result = apply_answer_validation(
                        result,
                        mode=normalized_answer_mode,
                        checker_source=checker_source,
                    )
                    results.append(
                        SolutionValidationCaseResult(
                            bucket="hidden",
                            index=index,
                            passed=scored_result.passed,
                            status=scored_result.status,
                            stdin=scored_result.input,
                            expected_output=scored_result.expected_output,
                            actual_output=scored_result.actual_output,
                            stderr=scored_result.stderr,
                            compile_output=scored_result.compile_output,
                            message=scored_result.message,
                            checker_message=scored_result.checker_message,
                            token=scored_result.token,
                            execution_time=scored_result.execution_time,
                            memory_kb=scored_result.memory_kb,
                        )
                    )
        except ExecutionAdapterError as exc:
            return SolutionValidationReport(
                status=ValidationStatus.FAILED.value,
                summary=f"Execution validation failed: {str(exc)}",
                passed_count=0,
                failed_count=len(sample_tests) + len(hidden_tests),
                sample_count=len(sample_tests),
                hidden_count=len(hidden_tests),
                runner_notes=[
                    str(exc),
                    "Ensure the code-execution-service is running and healthy.",
                ],
                results=[],
                rounds=rounds,
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

    def _execute_streamed_validation_cases(
        self,
        *,
        progress_context: _ValidationProgressContext,
        validation_pass: int,
        bucket: Literal["sample", "hidden"],
        test_cases: list[TestCase],
        source_code: str,
        language: str,
        run_type: str,
        total_cases: int,
        overall_offset: int,
        time_limit_seconds: float | None,
        memory_limit_kb: int | None,
        answer_validation_mode: str | AnswerValidationMode,
        output_checker: str,
    ) -> list[SolutionValidationCaseResult]:
        """Execute a testcase bucket in one batch while streaming case updates."""

        case_results: list[SolutionValidationCaseResult] = []
        bucket_label = "Sample" if bucket == "sample" else "Hidden"
        for index, test_case in enumerate(test_cases, start=1):
            overall_index = overall_offset + index
            progress_context.callback(
                {
                    **self._validation_case_base_event(
                        validation_pass=validation_pass,
                        bucket=bucket,
                        index=index,
                        bucket_total=len(test_cases),
                        overall_index=overall_index,
                        overall_total=total_cases,
                        language=language,
                        test_case=test_case,
                    ),
                    "type": "validation_case_start",
                    "message": (
                        f"Running {bucket_label.lower()} test {index} of "
                        f"{len(test_cases)}."
                    ),
                    "test_outcome": "running",
                    "test_status": "Running",
                }
            )

        try:
            raw_results, _, _ = self._execution_adapter.execute_batch(
                source_code=source_code,
                language=language,
                test_cases=test_cases,
                run_type=run_type,
                time_limit_seconds=time_limit_seconds,
                memory_limit_kb=memory_limit_kb,
            )
        except Exception as exc:
            for index, test_case in enumerate(test_cases, start=1):
                progress_context.callback(
                    {
                        **self._validation_case_base_event(
                            validation_pass=validation_pass,
                            bucket=bucket,
                            index=index,
                            bucket_total=len(test_cases),
                            overall_index=overall_offset + index,
                            overall_total=total_cases,
                            language=language,
                            test_case=test_case,
                        ),
                        "type": "validation_case_result",
                        "message": f"{bucket_label} test {index} could not run.",
                        "test_outcome": "error",
                        "test_status": "Execution error",
                        "actual_output": "",
                        "error_message": str(exc),
                    }
                )
            raise

        raw_result_by_index = {result.index: result for result in raw_results}
        for index, test_case in enumerate(test_cases, start=1):
            base_event = self._validation_case_base_event(
                validation_pass=validation_pass,
                bucket=bucket,
                index=index,
                bucket_total=len(test_cases),
                overall_index=overall_offset + index,
                overall_total=total_cases,
                language=language,
                test_case=test_case,
            )
            raw_result = raw_result_by_index.get(index)
            if raw_result is None:
                case_result = SolutionValidationCaseResult(
                    bucket=bucket,
                    index=index,
                    passed=False,
                    status="Execution Error",
                    stdin=test_case.input,
                    expected_output=test_case.expected_output,
                    message="Execution service returned no result for this test case.",
                )
            else:
                result = apply_answer_validation(
                    raw_result,
                    mode=answer_validation_mode,
                    checker_source=output_checker,
                )
                case_result = SolutionValidationCaseResult(
                    bucket=bucket,
                    index=index,
                    passed=result.passed,
                    status=result.status,
                    stdin=result.input,
                    expected_output=result.expected_output,
                    actual_output=result.actual_output,
                    stderr=result.stderr,
                    compile_output=result.compile_output,
                    message=result.message,
                    checker_message=result.checker_message,
                    token=result.token,
                    execution_time=result.execution_time,
                    memory_kb=result.memory_kb,
                )
            case_results.append(case_result)
            outcome = self._validation_case_outcome(case_result)
            progress_context.callback(
                {
                    **base_event,
                    "type": "validation_case_result",
                    "message": (
                        f"{bucket_label} test {index} passed."
                        if outcome == "passed"
                        else (
                            f"{bucket_label} test {index} returned a wrong answer."
                            if outcome == "wrong"
                            else f"{bucket_label} test {index} returned an error."
                        )
                    ),
                    "test_outcome": outcome,
                    "test_status": case_result.status,
                    "actual_output": case_result.actual_output,
                    "error_message": (
                        case_result.checker_message
                        or case_result.message
                        or case_result.stderr
                        or case_result.compile_output
                    ),
                    "checker_message": case_result.checker_message,
                }
            )
        return case_results

    @staticmethod
    def _validation_case_base_event(
        *,
        validation_pass: int,
        bucket: Literal["sample", "hidden"],
        index: int,
        bucket_total: int,
        overall_index: int,
        overall_total: int,
        language: str,
        test_case: TestCase,
    ) -> dict[str, Any]:
        return {
            "validation_pass": validation_pass,
            "test_bucket": bucket,
            "test_index": index,
            "bucket_total": bucket_total,
            "overall_index": overall_index,
            "overall_total": overall_total,
            "test_language": language,
            "test_input": test_case.input,
            "expected_output": test_case.expected_output,
        }

    @staticmethod
    def _validation_case_outcome(
        result: SolutionValidationCaseResult,
    ) -> Literal["passed", "wrong", "error"]:
        if result.passed:
            return "passed"
        status = result.status.strip().lower()
        if (
            result.stderr.strip()
            or result.compile_output.strip()
            or any(
                marker in status
                for marker in (
                    "error",
                    "exception",
                    "time limit",
                    "memory limit",
                    "runtime",
                    "compilation",
                    "internal",
                )
            )
        ):
            return "error"
        return "wrong"


__all__ = ["QuestionAgentToolsMixin", "validation_progress_events"]
