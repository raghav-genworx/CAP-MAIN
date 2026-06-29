"""Judge0 HTTP boundary contract tests."""

import base64
import json
import logging
import unittest

import httpx

from config.settings import Settings
from core.exceptions.execution import Judge0ServiceError
from handlers.http_clients.judge0 import Judge0Client
from observability.logging.config import configure_logging


def _encoded(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


class Judge0ClientContractTests(unittest.IsolatedAsyncioTestCase):
    def _settings(self) -> Settings:
        return Settings(
            judge0_base_url="https://judge0.test",
            judge0_api_key="judge0-secret",
            judge0_auth_header="X-Judge0-Key",
            judge0_poll_interval_seconds=0,
            judge0_max_poll_attempts=2,
        )

    def test_transport_loggers_do_not_emit_request_urls_at_info(self) -> None:
        configure_logging("INFO")

        self.assertEqual(logging.getLogger("httpx").level, logging.WARNING)
        self.assertEqual(logging.getLogger("httpcore").level, logging.WARNING)
        self.assertEqual(logging.getLogger("httpx2").level, logging.WARNING)
        self.assertEqual(logging.getLogger("httpcore2").level, logging.WARNING)

    async def test_execute_encodes_payload_authenticates_and_decodes_result(
        self,
    ) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "POST":
                return httpx.Response(201, json={"token": "private-token"})
            return httpx.Response(
                200,
                json={
                    "token": "private-token",
                    "status": {"id": 3, "description": "Accepted"},
                    "stdout": _encoded("42\n"),
                    "stderr": _encoded(""),
                    "compile_output": None,
                    "message": _encoded("completed"),
                },
            )

        client = Judge0Client(
            self._settings(),
            transport=httpx.MockTransport(handler),
        )
        with self.assertLogs("handlers.http_clients.judge0", level="INFO") as logs:
            result = await client.execute(
                {
                    "source_code": "print(input())",
                    "language_id": 71,
                    "stdin": "42\n",
                    "expected_output": "42\n",
                }
            )

        self.assertEqual(result.stdout, "42\n")
        self.assertEqual(result.message, "completed")
        self.assertEqual(len(requests), 2)
        submission_request = requests[0]
        self.assertEqual(submission_request.url.path, "/submissions")
        self.assertEqual(submission_request.url.params["base64_encoded"], "true")
        self.assertEqual(submission_request.url.params["wait"], "false")
        self.assertEqual(submission_request.headers["X-Judge0-Key"], "judge0-secret")
        payload = json.loads(submission_request.content)
        self.assertEqual(payload["source_code"], _encoded("print(input())"))
        self.assertEqual(payload["stdin"], _encoded("42\n"))
        self.assertEqual(payload["expected_output"], _encoded("42\n"))
        self.assertNotIn("private-token", " ".join(logs.output))
        self.assertIn("token_fingerprint", " ".join(logs.output))

    async def test_invalid_json_is_translated_to_provider_error(self) -> None:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(200, text="not-json")
        )
        client = Judge0Client(self._settings(), transport=transport)

        with self.assertRaisesRegex(Judge0ServiceError, "invalid JSON"):
            await client.get_languages()

    async def test_provider_error_body_is_not_exposed(self) -> None:
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(
                422,
                json={"detail": "candidate source and provider-secret"},
            )
        )
        client = Judge0Client(self._settings(), transport=transport)

        with self.assertRaises(Judge0ServiceError) as raised:
            await client.get_languages()

        self.assertEqual(
            str(raised.exception), "Judge0 rejected the execution request."
        )
        self.assertNotIn("provider-secret", str(raised.exception))

    async def test_invalid_base64_result_is_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(201, json={"token": "token"})
            return httpx.Response(
                200,
                json={
                    "token": "token",
                    "status": {"id": 3, "description": "Accepted"},
                    "stdout": "%%%not-base64%%%",
                },
            )

        client = Judge0Client(
            self._settings(),
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaisesRegex(Judge0ServiceError, "invalid encoded"):
            await client.execute({"source_code": "print(1)", "language_id": 71})


if __name__ == "__main__":
    unittest.main()
