"""Environment-driven application settings."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from schemas.auth import FirebaseWebConfig

SERVICE_DIR = Path(__file__).resolve().parents[2]
WORKSPACE_DIR = SERVICE_DIR.parent


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(
            SERVICE_DIR / ".env",
            WORKSPACE_DIR / "frontend" / ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Core Assessment Platform Service"
    app_env: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    cors_allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="Comma-separated list of allowed CORS origins.",
    )
    firebase_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("FIREBASE_API_KEY", "VITE_FIREBASE_API_KEY"),
    )
    firebase_auth_domain: str = Field(
        default="",
        validation_alias=AliasChoices(
            "FIREBASE_AUTH_DOMAIN",
            "VITE_FIREBASE_AUTH_DOMAIN",
        ),
    )
    firebase_project_id: str = Field(
        default="",
        validation_alias=AliasChoices(
            "FIREBASE_PROJECT_ID",
            "VITE_FIREBASE_PROJECT_ID",
        ),
    )
    firebase_app_id: str = Field(
        default="",
        validation_alias=AliasChoices("FIREBASE_APP_ID", "VITE_FIREBASE_APP_ID"),
    )
    firebase_storage_bucket: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "FIREBASE_STORAGE_BUCKET",
            "VITE_FIREBASE_STORAGE_BUCKET",
        ),
    )
    firebase_messaging_sender_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "FIREBASE_MESSAGING_SENDER_ID",
            "VITE_FIREBASE_MESSAGING_SENDER_ID",
        ),
    )
    firebase_measurement_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "FIREBASE_MEASUREMENT_ID",
            "VITE_FIREBASE_MEASUREMENT_ID",
        ),
    )
    groq_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GROQ_API_KEY"),
    )
    groq_base_url: str = Field(
        default="https://api.groq.com/openai/v1",
        validation_alias=AliasChoices("GROQ_BASE_URL", "VITE_GROQ_BASE_URL"),
    )
    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        validation_alias=AliasChoices("GROQ_MODEL", "VITE_GROQ_MODEL"),
    )
    groq_retry_count: int = 3
    groq_retry_backoff_seconds: float = 0.5
    groq_request_timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    code_execution_api_base_url: str = Field(
        default="http://localhost:8003/api/v1",
        validation_alias=AliasChoices(
            "CODE_EXECUTION_API_BASE_URL",
            "VITE_CODE_EXECUTION_API_BASE_URL",
        ),
    )
    code_execution_request_timeout_seconds: float = Field(
        default=90.0,
        ge=1.0,
        le=300.0,
    )
    code_evaluation_api_base_url: str = Field(
        default="http://localhost:8004/api/v1",
        validation_alias=AliasChoices(
            "CODE_EVALUATION_API_BASE_URL",
            "VITE_CODE_EVALUATION_API_BASE_URL",
        ),
    )
    code_evaluation_request_timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=300.0,
    )
    internal_service_token: str = Field(
        default="change-me-local-internal-service-token",
        min_length=24,
        validation_alias=AliasChoices("INTERNAL_SERVICE_TOKEN"),
    )
    brevo_base_url: str = Field(
        default="https://api.brevo.com/v3",
        validation_alias=AliasChoices("BREVO_BASE_URL", "VITE_BREVO_BASE_URL"),
    )
    brevo_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("BREVO_API_KEY"),
    )
    brevo_sender_email: str = Field(
        default="",
        validation_alias=AliasChoices(
            "BREVO_SENDER_EMAIL",
            "VITE_BREVO_SENDER_EMAIL",
        ),
    )
    brevo_sender_name: str = Field(
        default="CAP Assessments",
        validation_alias=AliasChoices(
            "BREVO_SENDER_NAME",
            "VITE_BREVO_SENDER_NAME",
        ),
    )
    brevo_request_timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    app_base_url: str = Field(
        default="http://localhost:5173",
        validation_alias=AliasChoices("APP_BASE_URL", "VITE_APP_BASE_URL"),
    )
    invite_token_pepper: str = Field(
        default="change-me-local-invite-token-pepper",
        min_length=24,
        validation_alias=AliasChoices("INVITE_TOKEN_PEPPER"),
    )
    candidate_session_secret: str = Field(
        default="change-me-local-candidate-session-secret",
        min_length=24,
        validation_alias=AliasChoices("CANDIDATE_SESSION_SECRET"),
    )
    candidate_session_ttl_minutes: int = Field(
        default=240,
        ge=15,
        le=1_440,
    )
    database_url: str = (
        "postgresql+psycopg://cap_user:cap_password@localhost:55432/cap_core"
    )
    auto_create_recruiter_role: bool = True

    @model_validator(mode="after")
    def require_production_secrets(self) -> "Settings":
        """Reject local-only credentials in non-local deployments."""

        if self.app_env.lower() in {"development", "local", "test"}:
            return self

        local_defaults = {
            "INTERNAL_SERVICE_TOKEN": (
                self.internal_service_token,
                "change-me-local-internal-service-token",
            ),
            "INVITE_TOKEN_PEPPER": (
                self.invite_token_pepper,
                "change-me-local-invite-token-pepper",
            ),
            "CANDIDATE_SESSION_SECRET": (
                self.candidate_session_secret,
                "change-me-local-candidate-session-secret",
            ),
        }
        invalid = [
            name
            for name, (value, local_value) in local_defaults.items()
            if value == local_value
        ]
        if invalid:
            raise ValueError(
                f"Production secrets must be configured: {', '.join(invalid)}"
            )
        invalid_origins = [
            origin
            for origin in self.cors_origins
            if origin == "*" or not origin.startswith("https://")
        ]
        if invalid_origins:
            raise ValueError("Production CORS origins must use explicit HTTPS URLs")
        if not self.app_base_url.startswith("https://"):
            raise ValueError("APP_BASE_URL must use HTTPS outside local use")
        return self

    @property
    def cors_origins(self) -> list[str]:
        """Return configured CORS origins as a normalized list."""

        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def firebase_web_config(self) -> FirebaseWebConfig:
        """Return Firebase configuration consumed by the frontend SDK."""

        return FirebaseWebConfig(
            apiKey=self.firebase_api_key,
            authDomain=self.firebase_auth_domain,
            projectId=self.firebase_project_id,
            appId=self.firebase_app_id,
            storageBucket=self.firebase_storage_bucket,
            messagingSenderId=self.firebase_messaging_sender_id,
            measurementId=self.firebase_measurement_id,
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for dependency injection."""

    return Settings()
