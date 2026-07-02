"""Firebase ID token verification."""

from typing import Any

from fastapi.security import HTTPAuthorizationCredentials
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from config.settings import Settings
from core.exceptions.auth import AuthenticationError
from schemas.auth import FirebaseIdentity

FIREBASE_CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/"
    "securetoken@system.gserviceaccount.com"
)


class FirebaseAuthService:
    """Verify Firebase bearer tokens and normalize identity claims."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the service with runtime settings."""

        self._settings = settings

    def verify_credentials(
        self,
        credentials: HTTPAuthorizationCredentials | None,
    ) -> FirebaseIdentity:
        """Verify a FastAPI bearer credential as a Firebase ID token."""

        if credentials is None or credentials.scheme.lower() != "bearer":
            raise AuthenticationError("Missing bearer token")

        if not self._settings.firebase_project_id:
            raise AuthenticationError("Firebase project ID is not configured")

        try:
            decoded_token = id_token.verify_token(
                credentials.credentials,
                google_requests.Request(),
                audience=self._settings.firebase_project_id,
                certs_url=FIREBASE_CERTS_URL,
            )
        except Exception as exc:
            raise AuthenticationError("Invalid or expired Firebase token") from exc

        if not isinstance(decoded_token, dict):
            raise AuthenticationError("Invalid Firebase token payload")

        expected_issuer = (
            f"https://securetoken.google.com/{self._settings.firebase_project_id}"
        )
        if decoded_token.get("iss") != expected_issuer:
            raise AuthenticationError("Invalid Firebase token issuer")

        uid = decoded_token.get("user_id") or decoded_token.get("sub")
        if not uid or not isinstance(uid, str):
            raise AuthenticationError("Firebase token is missing a user ID")
        if not bool(decoded_token.get("email_verified", False)):
            raise AuthenticationError(
                "Verify your email address before accessing the recruiter portal"
            )

        return FirebaseIdentity(
            uid=uid,
            email=self._optional_string(decoded_token.get("email")),
            name=self._optional_string(decoded_token.get("name")),
            picture=self._optional_string(decoded_token.get("picture")),
            email_verified=bool(decoded_token.get("email_verified", False)),
        )

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        """Return a claim value only when it is a string."""

        return value if isinstance(value, str) else None
