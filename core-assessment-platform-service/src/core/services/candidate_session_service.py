"""Issue and verify short-lived candidate session JWTs."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from config.settings import Settings
from core.exceptions.assessment import CandidateSessionError
from schemas.candidate_portal import CandidateSessionClaims


class CandidateSessionService:
    """Small HS256 JWT helper for candidate portal sessions."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._secret = settings.candidate_session_secret.encode("utf-8")

    def issue_session(
        self,
        *,
        candidate_assessment_id: str,
        assessment_id: str,
        slot_id: str,
        candidate_id: str,
        expires_at: datetime,
    ) -> str:
        """Create a signed JWT for the candidate portal."""

        exp = int(expires_at.astimezone(UTC).timestamp())
        header: dict[str, object] = {"alg": "HS256", "typ": "JWT"}
        payload: dict[str, object] = {
            "candidate_assessment_id": candidate_assessment_id,
            "assessment_id": assessment_id,
            "slot_id": slot_id,
            "candidate_id": candidate_id,
            "exp": exp,
        }
        encoded_header = self._encode_segment(header)
        encoded_payload = self._encode_segment(payload)
        signature = self._sign(f"{encoded_header}.{encoded_payload}")
        return f"{encoded_header}.{encoded_payload}.{signature}"

    def verify_session(self, token: str) -> CandidateSessionClaims:
        """Verify a signed candidate JWT and return normalized claims."""

        try:
            encoded_header, encoded_payload, signature = token.split(".")
        except ValueError as exc:
            raise CandidateSessionError("Candidate session token is malformed") from exc

        expected_signature = self._sign(f"{encoded_header}.{encoded_payload}")
        if not hmac.compare_digest(signature, expected_signature):
            raise CandidateSessionError("Candidate session signature is invalid")

        try:
            payload = json.loads(self._decode_segment(encoded_payload))
        except (ValueError, json.JSONDecodeError) as exc:
            raise CandidateSessionError("Candidate session payload is invalid") from exc

        claims = CandidateSessionClaims.model_validate(payload)
        now = int(datetime.now(UTC).timestamp())
        if claims.exp <= now:
            raise CandidateSessionError("Candidate session has expired")

        return claims

    def expires_at_from_deadline(self, deadline_at: datetime) -> datetime:
        """Clamp candidate token expiry to both TTL and the assessment deadline."""

        now = datetime.now(UTC)
        ttl_deadline = now + timedelta(
            minutes=self._settings.candidate_session_ttl_minutes
        )
        return min(deadline_at.astimezone(UTC), ttl_deadline)

    @staticmethod
    def hash_invite_token(token: str, pepper: str) -> str:
        """Return the server-side stored invite-token hash."""

        digest = hashlib.sha256()
        digest.update(pepper.encode("utf-8"))
        digest.update(token.encode("utf-8"))
        return digest.hexdigest()

    @staticmethod
    def _encode_segment(payload: dict[str, object]) -> str:
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_segment(segment: str) -> str:
        padding = "=" * (-len(segment) % 4)
        return base64.urlsafe_b64decode((segment + padding).encode("ascii")).decode(
            "utf-8"
        )

    def _sign(self, value: str) -> str:
        signed = hmac.new(self._secret, value.encode("utf-8"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(signed).decode("ascii").rstrip("=")
