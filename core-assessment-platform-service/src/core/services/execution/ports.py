"""How the rest of the platform reaches code execution.

Two implementations behind one protocol, selected by ``EXECUTION_TRANSPORT``:

* ``HttpExecutionPort`` -- the original adapter, over HTTP. Retained as the
  extraction path.
* ``InProcessExecutionPort`` -- calls ``CodeExecutionService`` directly.

**Judge0 isolation is unaffected by this choice.** Neither port runs candidate
code. ``CodeExecutionService`` is itself only an adapter: it builds a submission
and hands it to an isolated Judge0 deployment over HTTP. Going in-process removes
one hop between two of our own processes and nothing else -- the sandbox boundary
is Judge0's, and it stays exactly where it was.
"""

from __future__ import annotations

from typing import Protocol

from config.settings import Settings
from core.exceptions.assessment import ExecutionAdapterError
from handlers.http_clients.execution import ExecutionAdapterService
from schemas.assessments import ExecutionCaseResult
from schemas.question_bank import TestCase
from utils.helpers.concurrency import run_async

#: Transport names accepted by ``EXECUTION_TRANSPORT``.
HTTP = "http"
IN_PROCESS = "inprocess"

BatchResult = tuple[list[ExecutionCaseResult], int, int]


class ExecutionPort(Protocol):
    """The batch execution capability, independent of how it is reached."""

    def execute_batch(
        self,
        *,
        source_code: str,
        language: str,
        test_cases: list[TestCase],
        run_type: str,
        time_limit_seconds: float | None = None,
        memory_limit_kb: int | None = None,
    ) -> BatchResult: ...


class InProcessExecutionPort:
    """Call ``CodeExecutionService`` in this process."""

    def __init__(self, settings: Settings) -> None:
        from core.services.execution.code_execution_service import CodeExecutionService

        self._settings = settings
        self._service = CodeExecutionService(settings)

    async def execute_batch_async(
        self,
        *,
        source_code: str,
        language: str,
        test_cases: list[TestCase],
        run_type: str,
        time_limit_seconds: float | None = None,
        memory_limit_kb: int | None = None,
    ) -> BatchResult:
        """Execute one source against many test cases without leaving the process."""

        from schemas.execution import BatchExecutionRequest, BatchTestCase

        # Mirrors the guards the HTTP adapter applies before spending a request, so
        # both transports reject the same inputs with the same error.
        if not test_cases:
            return [], 0, 0
        if not source_code.strip():
            raise ExecutionAdapterError("Execution batch skipped: source code is empty")
        if not language.strip():
            raise ExecutionAdapterError("Execution batch skipped: language is empty")

        runnable = [
            BatchTestCase(input=case.input, expected_output=case.expected_output)
            for case in test_cases
            if case.expected_output.strip()
        ]
        if not runnable:
            return [], 0, 0

        request = BatchExecutionRequest(
            source_code=source_code.strip(),
            language=language.strip().lower(),
            run_type=run_type,
            test_cases=runnable,
            cpu_time_limit=time_limit_seconds,
            memory_limit=memory_limit_kb,
        )

        try:
            response = await self._service.execute_batch(request)
        except Exception as exc:
            # The HTTP transport surfaces every upstream failure as
            # ExecutionAdapterError; callers branch on it, so in-process must not
            # leak Judge0ServiceError or UnsupportedLanguageError in its place.
            raise ExecutionAdapterError("Execution service request failed") from exc

        results = [
            ExecutionCaseResult(
                index=index,
                input=case.input,
                expected_output=case.expected_output,
                actual_output=case.actual_output,
                status=case.status,
                passed=case.passed,
                stderr=case.stderr,
                compile_output=case.compile_output,
                message=case.message,
                execution_time=case.execution_time,
                memory_kb=case.memory_kb,
                token=case.token,
            )
            for index, case in enumerate(response.results, start=1)
        ]
        return results, response.passed_count, response.total_count

    def execute_batch(
        self,
        *,
        source_code: str,
        language: str,
        test_cases: list[TestCase],
        run_type: str,
        time_limit_seconds: float | None = None,
        memory_limit_kb: int | None = None,
    ) -> BatchResult:
        """Synchronous entry point for the still-synchronous service layer."""

        return run_async(
            self.execute_batch_async,
            source_code=source_code,
            language=language,
            test_cases=test_cases,
            run_type=run_type,
            time_limit_seconds=time_limit_seconds,
            memory_limit_kb=memory_limit_kb,
        )


class HttpExecutionPort(ExecutionAdapterService):
    """Call the execution service over HTTP."""


def build_execution_port(settings: Settings) -> ExecutionPort:
    """Return the execution port selected by ``EXECUTION_TRANSPORT``."""

    if settings.execution_transport == IN_PROCESS:
        return InProcessExecutionPort(settings)
    return HttpExecutionPort(settings)
