"""Business logic for executing user-submitted code."""

import logging

from config.settings import Settings
from constants.languages import (
    COMPILED_JUDGE0_LANGUAGE_IDS,
    JAVA_JUDGE0_LANGUAGE_ID,
    JUDGE0_LANGUAGE_ALIASES,
    SUPPORTED_JUDGE0_LANGUAGE_IDS,
)
from core.exceptions.execution import Judge0ServiceError, UnsupportedLanguageError
from handlers.http_clients.judge0 import Judge0Client
from schemas.execution import (
    BatchExecutionCaseResult,
    BatchExecutionRequest,
    BatchExecutionResponse,
    BatchTestCase,
    ExecutionRequest,
    ExecutionResponse,
    Judge0Payload,
    Judge0SubmissionResult,
    LanguageResponse,
)

logger = logging.getLogger(__name__)


class CodeExecutionService:
    """Coordinates request validation and Judge0 submission execution."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the execution service."""

        self._settings = settings
        self._judge0_client = Judge0Client(settings)

    async def execute(self, request: ExecutionRequest) -> ExecutionResponse:
        """Execute source code with the configured Judge0 backend."""

        payload = self._build_payload(request)
        result = await self._judge0_client.execute(payload)
        if result.status is None:
            raise Judge0ServiceError(
                "Judge0 returned a result without execution status."
            )
        return ExecutionResponse(
            token=result.token,
            status=result.status,
            stdout=self._bounded_output(result.stdout),
            stderr=self._bounded_output(result.stderr),
            compile_output=self._bounded_output(result.compile_output),
            message=self._bounded_output(result.message),
            time=result.time,
            wall_time=result.wall_time,
            memory=result.memory,
            exit_code=result.exit_code,
            exit_signal=result.exit_signal,
        )

    async def get_languages(self) -> list[LanguageResponse]:
        """Return supported languages from the configured Judge0 backend."""

        languages = await self._judge0_client.get_languages()
        return [
            language
            for language in languages
            if language.id in SUPPORTED_JUDGE0_LANGUAGE_IDS
        ]

    async def execute_batch(
        self,
        request: BatchExecutionRequest,
    ) -> BatchExecutionResponse:
        """Execute one source against multiple stdin/expected-output pairs."""

        payloads = [
            self._build_payload(
                ExecutionRequest(
                    source_code=request.source_code,
                    language_id=request.language_id,
                    language=request.language,
                    stdin=test_case.input,
                    expected_output=test_case.expected_output,
                    cpu_time_limit=request.cpu_time_limit,
                    memory_limit=request.memory_limit,
                )
            )
            for test_case in request.test_cases
        ]
        try:
            judge0_results = await self._judge0_client.execute_batch(payloads)
        except Judge0ServiceError as exc:
            logger.warning(
                "judge0_batch_rejected_falling_back_to_single_submissions "
                "run_type=%s case_count=%s message=%s",
                request.run_type,
                len(payloads),
                exc.message,
            )
            return await self._execute_batch_individually(
                request=request,
                payloads=payloads,
            )

        if len(judge0_results) != len(request.test_cases):
            raise Judge0ServiceError("Judge0 returned an incomplete batch response.")

        results: list[BatchExecutionCaseResult] = []
        passed_count = 0
        for test_case, result in zip(
            request.test_cases,
            judge0_results,
            strict=True,
        ):
            case_result = self._case_result_from_judge0(test_case, result)
            if case_result.passed:
                passed_count += 1
            results.append(case_result)
        return BatchExecutionResponse(
            run_type=request.run_type,
            passed_count=passed_count,
            total_count=len(results),
            results=results,
        )

    async def _execute_batch_individually(
        self,
        *,
        request: BatchExecutionRequest,
        payloads: list[Judge0Payload],
    ) -> BatchExecutionResponse:
        """Retry a rejected batch one case at a time and preserve partial results."""

        results: list[BatchExecutionCaseResult] = []
        passed_count = 0
        for test_case, payload in zip(request.test_cases, payloads, strict=True):
            try:
                judge0_result = await self._judge0_client.execute(payload)
            except Judge0ServiceError as exc:
                results.append(self._case_result_from_error(test_case, exc))
                continue

            case_result = self._case_result_from_judge0(test_case, judge0_result)
            if case_result.passed:
                passed_count += 1
            results.append(case_result)

        return BatchExecutionResponse(
            run_type=request.run_type,
            passed_count=passed_count,
            total_count=len(results),
            results=results,
        )

    def _case_result_from_judge0(
        self,
        test_case: BatchTestCase,
        result: Judge0SubmissionResult,
    ) -> BatchExecutionCaseResult:
        """Normalize one Judge0 result into the public batch response shape."""

        if result.status is None:
            raise Judge0ServiceError(
                "Judge0 returned a result without execution status."
            )

        status = result.status.description
        normalized_passed = self._outputs_match_with_safe_normalization(
            result.stdout or "",
            test_case.expected_output,
        )
        normalized_status = status.strip().lower()
        passed = normalized_status == "accepted" or (
            normalized_status == "wrong answer" and normalized_passed
        )
        if normalized_passed and normalized_status == "wrong answer":
            status = "Accepted (normalized trailing whitespace)"

        return BatchExecutionCaseResult(
            input=test_case.input,
            expected_output=test_case.expected_output,
            actual_output=self._bounded_output((result.stdout or "").strip()) or "",
            status=status,
            passed=passed,
            stderr=self._bounded_output((result.stderr or "").strip()) or "",
            compile_output=(
                self._bounded_output((result.compile_output or "").strip()) or ""
            ),
            message=self._bounded_output((result.message or "").strip()) or "",
            execution_time=str(result.time or ""),
            memory_kb=result.memory,
            token=result.token,
        )

    @staticmethod
    def _case_result_from_error(
        test_case: BatchTestCase,
        error: Judge0ServiceError,
    ) -> BatchExecutionCaseResult:
        """Represent a Judge0 submission rejection as a failed testcase result."""

        return BatchExecutionCaseResult(
            input=test_case.input,
            expected_output=test_case.expected_output,
            status="Execution Error",
            passed=False,
            message=error.message,
        )

    @staticmethod
    def _outputs_match_with_safe_normalization(
        actual_output: str,
        expected_output: str,
    ) -> bool:
        """Ignore only trailing whitespace/line-ending noise, not content formatting."""

        def normalize(value: str) -> str:
            return value.replace("\r\n", "\n").replace("\r", "\n").rstrip()

        return normalize(actual_output) == normalize(expected_output)

    def _build_payload(self, request: ExecutionRequest) -> Judge0Payload:
        language_id = request.language_id or self._language_id_for_alias(
            request.language
        )
        if language_id not in SUPPORTED_JUDGE0_LANGUAGE_IDS:
            raise UnsupportedLanguageError(str(language_id))
        payload: Judge0Payload = {
            "source_code": request.source_code,
            "language_id": language_id,
            "stdin": request.stdin,
            "expected_output": request.expected_output,
            "command_line_arguments": request.command_line_arguments,
            "cpu_time_limit": (
                request.cpu_time_limit or self._settings.default_cpu_time_limit_seconds
            ),
            "memory_limit": self._memory_limit_for_language(
                language_id,
                request.memory_limit,
            ),
        }
        if language_id in COMPILED_JUDGE0_LANGUAGE_IDS:
            payload["compiler_options"] = request.compiler_options
        return {key: value for key, value in payload.items() if value is not None}

    def _memory_limit_for_language(
        self,
        language_id: int,
        requested_limit_kb: int | None,
    ) -> int:
        requested = requested_limit_kb or self._settings.default_memory_limit_kb
        if language_id == JAVA_JUDGE0_LANGUAGE_ID:
            return max(requested, self._settings.java_minimum_memory_limit_kb)
        return requested

    def _bounded_output(self, value: str | None) -> str | None:
        if value is None or len(value) <= self._settings.max_output_characters:
            return value
        omitted = len(value) - self._settings.max_output_characters
        return (
            value[: self._settings.max_output_characters]
            + f"\n...[output truncated; {omitted} characters omitted]"
        )

    def _language_id_for_alias(self, language: str | None) -> int:
        if language is None:
            raise UnsupportedLanguageError("")
        language_id = JUDGE0_LANGUAGE_ALIASES.get(language.strip().lower())
        if language_id is None:
            raise UnsupportedLanguageError(language)
        return language_id
