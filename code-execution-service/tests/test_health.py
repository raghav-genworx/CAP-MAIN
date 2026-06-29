"""Execution readiness contract tests."""

import unittest
from unittest.mock import AsyncMock

from fastapi import Response

from api.rest.routes.health import health
from config.settings import Settings
from core.exceptions.execution import Judge0ServiceError


class ExecutionHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_is_degraded_when_judge0_is_unavailable(self) -> None:
        service = AsyncMock()
        service.get_languages.side_effect = Judge0ServiceError("unavailable")
        response = Response()

        payload = await health(Settings(), service, response)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload.status, "degraded")


if __name__ == "__main__":
    unittest.main()
