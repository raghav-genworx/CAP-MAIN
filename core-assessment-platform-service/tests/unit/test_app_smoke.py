"""Application wiring and cross-cutting response contracts.

These assert the shared behaviours every frontend request depends on, independently
of any single feature: the health payload, request correlation, and the
``{detail, trace_id}`` error envelope parsed in ``frontend/src/lib/axios.ts``.
"""

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

HEALTH_PATH = "/api/v1/health"
VERIFY_INVITE_PATH = "/api/v1/candidate/verify-invite"

# Correlation-ID behaviour belongs to the middleware, so assert it on a route that
# does not probe PostgreSQL. /health does, and would dominate the runtime.
MIDDLEWARE_PATH = "/metrics"


def test_health_returns_the_documented_payload(client: TestClient) -> None:
    """Health reports service metadata whether or not PostgreSQL is reachable."""

    response = client.get(HEALTH_PATH)

    # 503 with status "degraded" is the documented response when the database
    # probe fails, so this passes with or without a local PostgreSQL.
    assert response.status_code in {200, 503}
    payload = response.json()
    assert set(payload) == {"service", "environment", "status", "version"}
    assert payload["status"] in {"ok", "degraded"}
    assert (payload["status"] == "ok") == (response.status_code == 200)


def test_every_response_carries_a_request_id(client: TestClient) -> None:
    """The logging middleware echoes a correlation ID the frontend can surface."""

    response = client.get(MIDDLEWARE_PATH)

    assert response.headers["X-Request-ID"]


def test_a_safe_client_request_id_is_preserved(client: TestClient) -> None:
    """A well-formed client-supplied correlation ID is reused, not replaced."""

    response = client.get(MIDDLEWARE_PATH, headers={"X-Request-ID": "trace-123_abc.1"})

    assert response.headers["X-Request-ID"] == "trace-123_abc.1"


def test_an_unsafe_client_request_id_is_replaced(client: TestClient) -> None:
    """A malformed correlation ID is discarded so it cannot poison log lines."""

    injected = "bad id\nwith newline"

    response = client.get(MIDDLEWARE_PATH, headers={"X-Request-ID": injected})

    assert response.headers["X-Request-ID"] != injected


def test_validation_errors_use_the_frontend_error_envelope(
    client: TestClient,
) -> None:
    """A 422 carries `detail` and `trace_id` and never echoes the rejected input.

    ``verify-invite`` is one of the two public routes, so this exercises the
    envelope without any authentication or database access.
    """

    response = client.post(VERIFY_INVITE_PATH, json={"token": "too-short"})

    assert response.status_code == 422
    payload = response.json()
    assert set(payload) == {"detail", "trace_id"}
    assert payload["trace_id"] == response.headers["X-Request-ID"]
    assert isinstance(payload["detail"], list)
    for error in payload["detail"]:
        assert not {"input", "ctx", "url"} & set(error)


def test_metrics_endpoint_is_exposed(client: TestClient) -> None:
    """Prometheus scraping works and the endpoint stays out of the OpenAPI schema."""

    response = client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "/metrics" not in client.get("/openapi.json").json()["paths"]
