"""Firebase identity verification policy tests."""

from unittest.mock import patch

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from config.settings import Settings
from core.exceptions.auth import AuthenticationError
from core.services.firebase_auth_service import FirebaseAuthService


def _credentials() -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials="token")


def _settings() -> Settings:
    return Settings(app_env="test", firebase_project_id="cap-project")


def test_unverified_email_is_rejected() -> None:
    payload = {
        "sub": "firebase-user",
        "iss": "https://securetoken.google.com/cap-project",
        "email": "recruiter@example.com",
        "email_verified": False,
    }

    with patch(
        "core.services.firebase_auth_service.id_token.verify_token",
        return_value=payload,
    ), pytest.raises(AuthenticationError, match="Verify your email"):
        FirebaseAuthService(_settings()).verify_credentials(_credentials())


def test_verified_email_is_accepted() -> None:
    payload = {
        "sub": "firebase-user",
        "iss": "https://securetoken.google.com/cap-project",
        "email": "recruiter@example.com",
        "email_verified": True,
    }

    with patch(
        "core.services.firebase_auth_service.id_token.verify_token",
        return_value=payload,
    ):
        identity = FirebaseAuthService(_settings()).verify_credentials(_credentials())

    assert identity.uid == "firebase-user"
    assert identity.email_verified is True
