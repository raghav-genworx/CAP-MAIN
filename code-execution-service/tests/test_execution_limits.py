"""Regression coverage for execution output and polling budgets."""

from unittest import TestCase

from config.settings import Settings
from core.services.code_execution_service import CodeExecutionService
from handlers.http_clients.judge0 import Judge0Client
from schemas.execution import ExecutionRequest


class ExecutionLimitTests(TestCase):
    def test_large_output_is_truncated_with_notice(self) -> None:
        settings = Settings(max_output_characters=1_000)
        service = CodeExecutionService(settings)
        bounded = service._bounded_output("x" * 1_250)
        self.assertIsNotNone(bounded)
        assert bounded is not None
        self.assertLess(len(bounded), 1_100)
        self.assertIn("output truncated", bounded)
        self.assertIn("250 characters omitted", bounded)

    def test_poll_budget_covers_cpu_limit_plus_margin(self) -> None:
        settings = Settings(
            judge0_poll_interval_seconds=0.5,
            judge0_max_poll_attempts=4,
            judge0_poll_margin_seconds=5,
        )
        client = Judge0Client(settings)
        attempts = client._poll_attempt_budget(cpu_time_limit=30)
        self.assertGreaterEqual(attempts * 0.5, 35)

    def test_poll_budget_keeps_configured_minimum(self) -> None:
        settings = Settings(
            judge0_poll_interval_seconds=0.5,
            judge0_max_poll_attempts=30,
            judge0_poll_margin_seconds=5,
        )
        client = Judge0Client(settings)
        self.assertGreaterEqual(client._poll_attempt_budget(2), 30)

    def test_java_receives_room_for_vm_overhead(self) -> None:
        service = CodeExecutionService(Settings(java_minimum_memory_limit_kb=512000))
        payload = service._build_payload(
            ExecutionRequest(
                source_code="class Main {}",
                language="java",
                memory_limit=256 * 1024,
            )
        )
        self.assertEqual(payload["memory_limit"], 512000)
        self.assertEqual(payload["language_id"], 1003)

    def test_non_java_memory_limit_is_not_inflated(self) -> None:
        service = CodeExecutionService(Settings(java_minimum_memory_limit_kb=512000))
        payload = service._build_payload(
            ExecutionRequest(
                source_code="print(1)",
                language="python",
                memory_limit=128000,
            )
        )
        self.assertEqual(payload["memory_limit"], 128000)
