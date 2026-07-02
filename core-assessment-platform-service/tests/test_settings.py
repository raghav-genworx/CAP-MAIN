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


def test_langsmith_settings_use_documented_environment_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "https://smith.example.test")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-langsmith-key")
    monkeypatch.setenv("LANGSMITH_PROJECT", "CAP")

    settings = Settings()

    assert settings.langsmith_tracing is True
    assert settings.langsmith_endpoint == "https://smith.example.test"
    assert settings.langsmith_api_key == "test-langsmith-key"
    assert settings.langsmith_project == "CAP"


def test_ai_gateway_key_slots_preserve_order_and_legacy_key() -> None:
    settings = Settings(
        groq_api_key="legacy-slot-one",
        groq_api_key_2="slot-two",
        groq_api_key_3="",
        groq_api_key_4="slot-four",
    )

    assert settings.groq_api_key_slots == [
        (1, "legacy-slot-one"),
        (2, "slot-two"),
        (4, "slot-four"),
    ]
    assert settings.groq_api_keys == [
        "legacy-slot-one",
        "slot-two",
        "slot-four",
    ]


def test_ai_gateway_model_sequence_defaults_to_qwen_gpt_oss_then_ollama() -> None:
    settings = Settings()

    assert settings.groq_fallback_models == [
        "qwen/qwen3-32b",
        "openai/gpt-oss-120b",
    ]
    assert settings.ai_model_sequence_label == (
        "groq:qwen/qwen3-32b -> groq:openai/gpt-oss-120b -> ollama:llama3.3:70b"
    )
