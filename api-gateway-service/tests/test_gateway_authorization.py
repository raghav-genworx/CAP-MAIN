"""Gateway authentication and trusted-proxy contract tests."""

import asyncio
import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from config.settings import Settings
from core.exceptions.gateway import (
    GatewayAuthenticationError,
    UnknownUpstreamServiceError,
)
from core.services.gateway_auth_service import GatewayAuthService
from core.services.gateway_service import GatewayService

CANDIDATE_SECRET = "candidate-session-test-secret-value"
INTERNAL_TOKEN = "internal-service-test-token-value"


def _settings() -> Settings:
    return Settings(
        app_env="test",
        core_service_base_url="http://core.test",
        code_execution_service_base_url="http://execution.test",
        code_evaluation_service_base_url="http://evaluation.test",
        candidate_session_secret=CANDIDATE_SECRET,
        internal_service_token=INTERNAL_TOKEN,
    )


def _encode(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _candidate_token(expires_at: datetime) -> str:
    header = _encode({"alg": "HS256", "typ": "JWT"})
    payload = _encode(
        {
            "assessment_id": "assessment-1",
            "candidate_assessment_id": "assignment-1",
            "candidate_id": "candidate-1",
            "exp": int(expires_at.timestamp()),
            "slot_id": "slot-1",
        }
    )
    value = f"{header}.{payload}"
    signature = hmac.new(
        CANDIDATE_SECRET.encode(),
        value.encode(),
        hashlib.sha256,
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{value}.{encoded_signature}"


def test_public_invite_route_does_not_require_bearer_token() -> None:
    service = GatewayAuthService(_settings())

    asyncio.run(
        service.authorize(
            service_name="core",
            path="candidate/verify-invite",
            method="POST",
            authorization=None,
        )
    )


def test_unknown_service_is_rejected_before_proxying() -> None:
    service = GatewayAuthService(_settings())

    with pytest.raises(UnknownUpstreamServiceError):
        asyncio.run(
            service.authorize(
                service_name="browser-selected-host",
                path="health",
                method="GET",
                authorization=None,
            )
        )


def test_candidate_route_verifies_signed_session() -> None:
    service = GatewayAuthService(_settings())
    token = _candidate_token(datetime.now(UTC) + timedelta(minutes=5))

    asyncio.run(
        service.authorize(
            service_name="core",
            path="candidate/assessment",
            method="GET",
            authorization=f"Bearer {token}",
        )
    )


def test_candidate_route_rejects_expired_session() -> None:
    service = GatewayAuthService(_settings())
    token = _candidate_token(datetime.now(UTC) - timedelta(minutes=1))

    with pytest.raises(GatewayAuthenticationError, match="expired"):
        asyncio.run(
            service.authorize(
                service_name="core",
                path="candidate/assessment",
                method="GET",
                authorization=f"Bearer {token}",
            )
        )


def test_recruiter_route_requires_core_authorized_role() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer firebase-token"
        return httpx.Response(200, json={"uid": "user-1", "role": "recruiter"})

    service = GatewayAuthService(
        _settings(),
        transport=httpx.MockTransport(handler),
    )

    asyncio.run(
        service.authorize(
            service_name="core",
            path="assessments",
            method="GET",
            authorization="Bearer firebase-token",
        )
    )


def test_proxy_replaces_browser_internal_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://execution.test/api/v1/executions?limit=10"
        assert request.headers["x-internal-service-token"] == INTERNAL_TOKEN
        assert request.headers["authorization"] == "Bearer firebase-token"
        return httpx.Response(200, json={"status": "ok"})

    async def exercise() -> None:
        service = GatewayService(
            _settings(),
            transport=httpx.MockTransport(handler),
        )
        client, response = await service.open_proxy_response(
            service_name="code-execution",
            path="executions",
            method="GET",
            query="limit=10",
            headers={
                "Authorization": "Bearer firebase-token",
                "X-Internal-Service-Token": "browser-controlled-token",
            },
            body=b"",
        )
        assert response.status_code == 200
        assert await response.aread() == b'{"status":"ok"}'
        await service.close_proxy_response(client, response)

    asyncio.run(exercise())
