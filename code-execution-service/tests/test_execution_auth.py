"""Execution service trust-boundary tests."""

import unittest

from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.rest.app import create_app
from config.settings import Settings


class ExecutionAuthenticationTests(unittest.TestCase):
    """Verify code execution is available only to trusted services."""

    def test_execution_route_rejects_untrusted_requests(self) -> None:
        client = TestClient(create_app())

        response = client.get("/api/v1/executions/languages")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Unauthorized service request")
        self.assertIn("trace_id", response.json())

    def test_production_rejects_local_internal_service_token(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                app_env="production",
                internal_service_token="change-me-local-internal-service-token",
            )

    def test_production_rejects_insecure_browser_origins(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                app_env="production",
                internal_service_token="production-internal-service-token",
                cors_allowed_origins="http://cap.example.com",
            )


if __name__ == "__main__":
    unittest.main()
