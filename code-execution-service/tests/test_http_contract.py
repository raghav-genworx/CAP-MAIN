"""HTTP observability contract tests."""

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.middleware.error_handler import setup_error_handlers
from api.middleware.logging import setup_request_logging


def _test_app() -> FastAPI:
    app = FastAPI()
    setup_error_handlers(app)
    setup_request_logging(app)

    @app.get("/items/{item_id}")
    async def get_item(item_id: int) -> dict[str, int]:
        return {"item_id": item_id}

    return app


class HttpContractTests(unittest.TestCase):
    """Verify request correlation and safe validation failures."""

    def test_request_id_is_generated_and_propagated(self) -> None:
        client = TestClient(_test_app())

        generated = client.get("/items/1")
        propagated = client.get(
            "/items/2",
            headers={"X-Request-ID": "execution-contract-42"},
        )

        self.assertRegex(generated.headers["x-request-id"], r"^[a-f0-9]{32}$")
        self.assertEqual(
            propagated.headers["x-request-id"],
            "execution-contract-42",
        )

    def test_validation_error_contains_trace_id(self) -> None:
        client = TestClient(_test_app())

        response = client.get(
            "/items/not-an-integer",
            headers={"X-Request-ID": "execution-validation-42"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["trace_id"], "execution-validation-42")
        self.assertNotIn("input", str(response.json()["detail"]))


if __name__ == "__main__":
    unittest.main()
