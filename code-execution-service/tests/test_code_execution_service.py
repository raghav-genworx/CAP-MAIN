"""Code execution scoring safety tests."""

import unittest
from unittest.mock import AsyncMock

from config.settings import Settings
from core.services.code_execution_service import CodeExecutionService
from schemas.execution import (
    BatchExecutionRequest,
    BatchTestCase,
    Judge0Status,
    Judge0SubmissionResult,
)


class CodeExecutionServiceTests(unittest.IsolatedAsyncioTestCase):
    """Verify verdict normalization never converts execution failures to passes."""

    def setUp(self) -> None:
        self.service = CodeExecutionService(Settings())
        self.service._judge0_client.execute = AsyncMock()  # type: ignore[method-assign]

    async def test_compile_error_with_empty_output_is_not_passed(self) -> None:
        self.service._judge0_client.execute.return_value = Judge0SubmissionResult(
            token="judge-token",
            status=Judge0Status(id=6, description="Compilation Error"),
            stdout="",
            compile_output="syntax error",
        )

        response = await self.service.execute_batch(self._request(expected_output=""))

        self.assertEqual(response.passed_count, 0)
        self.assertFalse(response.results[0].passed)
        self.assertEqual(response.results[0].status, "Compilation Error")

    async def test_only_wrong_answer_can_use_whitespace_normalization(self) -> None:
        self.service._judge0_client.execute.return_value = Judge0SubmissionResult(
            token="judge-token",
            status=Judge0Status(id=4, description="Wrong Answer"),
            stdout="42\n\n",
        )

        response = await self.service.execute_batch(
            self._request(expected_output="42\n")
        )

        self.assertEqual(response.passed_count, 1)
        self.assertTrue(response.results[0].passed)
        self.assertEqual(
            response.results[0].status,
            "Accepted (normalized trailing whitespace)",
        )

    async def test_runtime_error_cannot_pass_on_matching_partial_output(self) -> None:
        self.service._judge0_client.execute.return_value = Judge0SubmissionResult(
            token="judge-token",
            status=Judge0Status(id=11, description="Runtime Error (NZEC)"),
            stdout="42\n",
            stderr="process exited with status 1",
        )

        response = await self.service.execute_batch(
            self._request(expected_output="42\n")
        )

        self.assertEqual(response.passed_count, 0)
        self.assertFalse(response.results[0].passed)

    @staticmethod
    def _request(*, expected_output: str) -> BatchExecutionRequest:
        return BatchExecutionRequest(
            source_code="print(42)",
            language="python",
            test_cases=[BatchTestCase(input="", expected_output=expected_output)],
        )


if __name__ == "__main__":
    unittest.main()
