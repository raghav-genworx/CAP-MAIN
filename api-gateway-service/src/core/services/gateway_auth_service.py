"""Gateway authentication and route authorization policy."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

import httpx
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from config.settings import Settings
from core.exceptions.gateway import (
    GatewayAuthenticationError,
    GatewayAuthorizationError,
    UnknownUpstreamServiceError,
    UpstreamServiceUnavailableError,
)

FIREBASE_CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/"
    "securetoken@system.gserviceaccount.com"
)

PUBLIC_CORE_ROUTES = {
    ("GET", "auth/firebase-config"),
    ("POST", "candidate/start"),
    ("POST", "candidate/verify-invite"),
}

ONBOARDING_CORE_ROUTES = {
    ("GET", "auth/me"),
    ("POST", "auth/start-free-trial"),
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
    ) -> dict[str, str]:
        """Apply public, candidate, or recruiter authorization policy.

        Returns a dictionary of headers to inject into the upstream request.
        """

        if service_name not in self._settings.upstream_services:
            raise UnknownUpstreamServiceError(service_name)

        normalized_path = path.strip("/")
        normalized_method = method.upper()
        if (
            service_name == "core"
            and (
                normalized_method,
                normalized_path,
            )
            in PUBLIC_CORE_ROUTES
        ):
            return {}

        token = self._bearer_token(authorization)
        if service_name == "core" and normalized_path.startswith("candidate/"):
            self._verify_candidate_session(token)
            return {}

        require_subscription = not (
            service_name == "core"
            and (normalized_method, normalized_path) in ONBOARDING_CORE_ROUTES
        )
        return await self._authorize_recruiter(
            authorization,
            require_subscription=require_subscription,
        )

    async def _authorize_recruiter(
        self,
        authorization: str | None,
        *,
        require_subscription: bool,
    ) -> dict[str, str]:
        """Verify Firebase token locally and check recruiter role with core service."""

        token = self._bearer_token(authorization)

        if not self._settings.firebase_project_id:
            raise GatewayAuthenticationError("Firebase project ID is not configured")

        try:
            decoded_token = await asyncio.to_thread(
                id_token.verify_token,
                token,
                google_requests.Request(),
                audience=self._settings.firebase_project_id,
                certs_url=FIREBASE_CERTS_URL,
            )
        except Exception as exc:
            raise GatewayAuthenticationError(
                "Invalid or expired recruiter token"
            ) from exc

        if not isinstance(decoded_token, dict):
            raise GatewayAuthenticationError("Invalid recruiter token payload")

        expected_issuer = (
            f"https://securetoken.google.com/{self._settings.firebase_project_id}"
        )
        if decoded_token.get("iss") != expected_issuer:
            raise GatewayAuthenticationError("Invalid recruiter token issuer")

        uid = decoded_token.get("user_id") or decoded_token.get("sub")
        if not uid or not isinstance(uid, str):
            raise GatewayAuthenticationError("Recruiter token is missing a user ID")
        if not bool(decoded_token.get("email_verified", False)):
            raise GatewayAuthenticationError(
                "Verify your email address before accessing the recruiter portal"
            )

        auth_headers = {
            "Authorization": authorization or "",
            "X-Internal-Service-Token": self._settings.internal_service_token,
            "X-User-Id": uid,
            "X-User-Email": decoded_token.get("email") or "",
            "X-User-Name": decoded_token.get("name") or "",
            "X-User-Picture": decoded_token.get("picture") or "",
            "X-User-Email-Verified": str(
                decoded_token.get("email_verified", False)
            ).lower(),
        }

        target_url = (
            f"{self._settings.core_service_base_url.rstrip('/')}/api/v1/auth/me"
        )
        try:
            async with httpx.AsyncClient(
                timeout=self._settings.upstream_request_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.get(
                    target_url,
                    headers=auth_headers,
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
        if require_subscription and payload.get("subscription_status") != "free_trial":
            raise GatewayAuthorizationError(
                "Start your free trial to access recruiter tools"
            )

        return auth_headers

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
