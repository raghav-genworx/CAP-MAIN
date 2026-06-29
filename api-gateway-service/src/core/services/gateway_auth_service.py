"""Gateway authentication and route authorization policy."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

import httpx

from config.settings import Settings
from core.exceptions.gateway import (
    GatewayAuthenticationError,
    GatewayAuthorizationError,
    UnknownUpstreamServiceError,
    UpstreamServiceUnavailableError,
)

PUBLIC_CORE_ROUTES = {
    ("GET", "auth/firebase-config"),
    ("POST", "candidate/start"),
    ("POST", "candidate/verify-invite"),
}


class GatewayAuthService:
    """Authorize browser traffic before it reaches an upstream service."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._transport = transport

    async def authorize(
        self,
        *,
        service_name: str,
        path: str,
        method: str,
        authorization: str | None,
    ) -> None:
        """Apply public, candidate, or recruiter authorization policy."""

        if service_name not in self._settings.upstream_services:
            raise UnknownUpstreamServiceError(service_name)

        normalized_path = path.strip("/")
        normalized_method = method.upper()
        if service_name == "core" and (
            normalized_method,
            normalized_path,
        ) in PUBLIC_CORE_ROUTES:
            return

        token = self._bearer_token(authorization)
        if service_name == "core" and normalized_path.startswith("candidate/"):
            self._verify_candidate_session(token)
            return

        await self._authorize_recruiter(authorization)

    async def _authorize_recruiter(self, authorization: str | None) -> None:
        """Ask the core auth authority to verify Firebase identity and role."""

        self._bearer_token(authorization)
        target_url = (
            f"{self._settings.core_service_base_url.rstrip('/')}"
            "/api/v1/auth/me"
        )
        try:
            async with httpx.AsyncClient(
                timeout=self._settings.upstream_request_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    target_url,
                    headers={"Authorization": authorization or ""},
                )
        except httpx.HTTPError as exc:
            raise UpstreamServiceUnavailableError("core-auth") from exc

        if response.status_code == 401:
            raise GatewayAuthenticationError("Invalid or expired recruiter token")
        if response.status_code == 403:
            raise GatewayAuthorizationError("Recruiter role is not authorized")
        if not response.is_success:
            raise UpstreamServiceUnavailableError("core-auth")

        try:
            payload = response.json()
        except ValueError as exc:
            raise UpstreamServiceUnavailableError("core-auth") from exc
        if not isinstance(payload, dict) or payload.get("role") != "recruiter":
            raise GatewayAuthorizationError("Recruiter role is required")

    def _verify_candidate_session(self, token: str) -> None:
        """Verify the signature, algorithm, claims, and expiry of a candidate JWT."""

        try:
            encoded_header, encoded_payload, signature = token.split(".")
            header = json.loads(self._decode_segment(encoded_header))
            payload = json.loads(self._decode_segment(encoded_payload))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GatewayAuthenticationError("Invalid candidate session token") from exc

        if not isinstance(header, dict) or header.get("alg") != "HS256":
            raise GatewayAuthenticationError("Invalid candidate session algorithm")
        if not isinstance(payload, dict):
            raise GatewayAuthenticationError("Invalid candidate session claims")

        expected = self._sign(f"{encoded_header}.{encoded_payload}")
        if not hmac.compare_digest(signature, expected):
            raise GatewayAuthenticationError("Invalid candidate session signature")

        required_strings = (
            "candidate_assessment_id",
            "assessment_id",
            "slot_id",
            "candidate_id",
        )
        invalid_claim = any(
            not self._non_empty_string(payload.get(key)) for key in required_strings
        )
        if invalid_claim:
            raise GatewayAuthenticationError("Invalid candidate session claims")

        expires_at = payload.get("exp")
        if not isinstance(expires_at, int):
            raise GatewayAuthenticationError("Invalid candidate session expiry")
        if expires_at <= int(datetime.now(UTC).timestamp()):
            raise GatewayAuthenticationError("Candidate session has expired")

    @staticmethod
    def _bearer_token(authorization: str | None) -> str:
        if not authorization:
            raise GatewayAuthenticationError("Missing bearer token")
        scheme, separator, token = authorization.partition(" ")
        if separator != " " or scheme.lower() != "bearer" or not token.strip():
            raise GatewayAuthenticationError("Invalid bearer token")
        return token.strip()

    @staticmethod
    def _non_empty_string(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    @staticmethod
    def _decode_segment(segment: str) -> str:
        padding = "=" * (-len(segment) % 4)
        return base64.urlsafe_b64decode((segment + padding).encode("ascii")).decode(
            "utf-8"
        )

    def _sign(self, value: str) -> str:
        digest = hmac.new(
            self._settings.candidate_session_secret.encode("utf-8"),
            value.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
