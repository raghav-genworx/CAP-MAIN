"""Adapter used by the core service to call code-execution-service."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from config.settings import Settings
from core.exceptions.assessment import ExecutionAdapterError
from schemas.assessments import ExecutionCaseResult
from schemas.question_bank import TestCase

logger = logging.getLogger(__name__)


class ExecutionAdapterService:
    """Call the batch execution API and normalize the result."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def execute_batch(
        self,
        *,
        source_code: str,
        language: str,
        test_cases: list[TestCase],
        run_type: str,
        time_limit_seconds: float | None = None,
        memory_limit_kb: int | None = None,
    ) -> tuple[list[ExecutionCaseResult], int, int]:
        """Execute one source against a list of test cases."""

        if not test_cases:
            return [], 0, 0
        if not source_code.strip():
            raise ExecutionAdapterError("Execution batch skipped: source code is empty")
        if not language.strip():
            raise ExecutionAdapterError("Execution batch skipped: language is empty")

        payload: dict[str, Any] = {
            "source_code": source_code.strip(),
            "language": language.strip().lower(),
            "run_type": run_type,
            "test_cases": [
                {
                    "input": case.input,
                    "expected_output": case.expected_output,
                }
                for case in test_cases
                if case.input.strip() and case.expected_output.strip()
            ],
        }
        if not payload["test_cases"]:
            return [], 0, 0
        if time_limit_seconds is not None:
            payload["cpu_time_limit"] = time_limit_seconds
        if memory_limit_kb is not None:
            payload["memory_limit"] = memory_limit_kb

        url = (
            f"{self._settings.code_execution_api_base_url.rstrip('/')}/executions/batch"
        )
        try:
            with httpx.Client(
                timeout=self._settings.code_execution_request_timeout_seconds,
                headers={
                    "X-Internal-Service-Token": self._settings.internal_service_token,
                },
            ) as client:
                response = client.post(url, json=payload)
                if response.is_error:
                    logger.error(
                        "execution_service_batch_error status_code=%s payload_shape=%s",
                        response.status_code,
                        self._payload_shape(payload),
                    )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ExecutionAdapterError("Execution service request failed") from exc

        data = response.json()
        raw_results = data.get("results", [])
        results = [
            ExecutionCaseResult(
                index=index,
                input=str(item.get("input") or ""),
                expected_output=str(item.get("expected_output") or ""),
                actual_output=str(item.get("actual_output") or ""),
                status=str(item.get("status") or "Unknown"),
                passed=bool(item.get("passed")),
                stderr=str(item.get("stderr") or ""),
                compile_output=str(item.get("compile_output") or ""),
                message=str(item.get("message") or ""),
                execution_time=str(item.get("execution_time") or ""),
                memory_kb=item.get("memory_kb"),
                token=str(item.get("token") or ""),
            )
            for index, item in enumerate(raw_results, start=1)
        ]
        return (
            results,
            int(data.get("passed_count") or 0),
            int(data.get("total_count") or 0),
        )

    @staticmethod
    def _payload_shape(payload: dict[str, Any]) -> dict[str, Any]:
        """Return diagnostic request metadata without logging candidate code."""

        test_cases = payload.get("test_cases")
        return {
            "keys": sorted(payload.keys()),
            "source_code_length": len(str(payload.get("source_code") or "")),
            "language": payload.get("language"),
            "run_type": payload.get("run_type"),
            "test_case_count": len(test_cases) if isinstance(test_cases, list) else 0,
            "test_case_keys": (
                sorted(test_cases[0].keys())
                if isinstance(test_cases, list)
                and test_cases
                and isinstance(test_cases[0], dict)
                else []
            ),
            "has_cpu_time_limit": "cpu_time_limit" in payload,
            "has_memory_limit": "memory_limit" in payload,
        }
