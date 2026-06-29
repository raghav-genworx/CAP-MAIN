"""Security-sensitive settings tests."""

import pytest
from pydantic import ValidationError

from config.settings import Settings


def test_production_rejects_documented_local_secrets() -> None:
    with pytest.raises(ValidationError, match="Production secrets must be configured"):
        Settings(
            app_env="production",
            internal_service_token="change-me-local-internal-service-token",
            invite_token_pepper="change-me-local-invite-token-pepper",
            candidate_session_secret="change-me-local-candidate-session-secret",
        )


def test_production_accepts_explicit_server_only_secrets() -> None:
    settings = Settings(
        app_env="production",
        internal_service_token="production-internal-token-value",
        invite_token_pepper="production-invite-token-pepper",
        candidate_session_secret="production-candidate-session-secret",
        cors_allowed_origins="https://cap.example.com",
        app_base_url="https://cap.example.com",
    )

    assert settings.internal_service_token == "production-internal-token-value"


def test_production_rejects_insecure_browser_origins() -> None:
    with pytest.raises(ValidationError, match="CORS origins"):
        Settings(
            app_env="production",
            internal_service_token="production-internal-token-value",
            invite_token_pepper="production-invite-token-pepper",
            candidate_session_secret="production-candidate-session-secret",
            cors_allowed_origins="http://cap.example.com",
            app_base_url="https://cap.example.com",
        )
