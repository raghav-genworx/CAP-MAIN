"""Business logic for executing user-submitted code."""

from config.settings import Settings
from constants.languages import (
    COMPILED_JUDGE0_LANGUAGE_IDS,
    JUDGE0_LANGUAGE_ALIASES,
    SUPPORTED_JUDGE0_LANGUAGE_IDS,
)
from core.exceptions.execution import Judge0ServiceError, UnsupportedLanguageError
from handlers.http_clients.judge0 import Judge0Client
from schemas.execution import (
    BatchExecutionCaseResult,
    BatchExecutionRequest,
    BatchExecutionResponse,
    ExecutionRequest,
    ExecutionResponse,
    Judge0Payload,
    LanguageResponse,
)


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
            stdout=result.stdout,
            stderr=result.stderr,
            compile_output=result.compile_output,
            message=result.message,
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

        results: list[BatchExecutionCaseResult] = []
        passed_count = 0
        for test_case in request.test_cases:
            payload = self._build_payload(
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
            result = await self._judge0_client.execute(payload)
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
            if passed:
                passed_count += 1
            results.append(
                BatchExecutionCaseResult(
                    input=test_case.input,
                    expected_output=test_case.expected_output,
                    actual_output=(result.stdout or "").strip(),
                    status=status,
                    passed=passed,
                    stderr=(result.stderr or "").strip(),
                    compile_output=(result.compile_output or "").strip(),
                    message=(result.message or "").strip(),
                    execution_time=str(result.time or ""),
                    memory_kb=result.memory,
                    token=result.token,
                )
            )
        return BatchExecutionResponse(
            run_type=request.run_type,
            passed_count=passed_count,
            total_count=len(results),
            results=results,
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
            "memory_limit": request.memory_limit
            or self._settings.default_memory_limit_kb,
        }
        if language_id in COMPILED_JUDGE0_LANGUAGE_IDS:
            payload["compiler_options"] = request.compiler_options
        return {key: value for key, value in payload.items() if value is not None}

    def _language_id_for_alias(self, language: str | None) -> int:
        if language is None:
            raise UnsupportedLanguageError("")
        language_id = JUDGE0_LANGUAGE_ALIASES.get(language.strip().lower())
        if language_id is None:
            raise UnsupportedLanguageError(language)
        return language_id
