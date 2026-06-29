"""Environment-driven application settings."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "API Gateway Service"
    app_env: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    cors_allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="Comma-separated list of allowed CORS origins.",
    )
    core_service_base_url: str = Field(
        default="http://localhost:8002",
        description="Base URL for the core platform service.",
    )
    code_execution_service_base_url: str = Field(
        default="http://localhost:8003",
        description="Base URL for the code execution service.",
    )
    code_evaluation_service_base_url: str = Field(
        default="http://localhost:8004",
        description="Base URL for the code evaluation service.",
    )
    internal_service_token: str = Field(
        default="change-me-local-internal-service-token",
        min_length=24,
        description="Credential injected only into trusted internal requests.",
    )
    candidate_session_secret: str = Field(
        default="change-me-local-candidate-session-secret",
        min_length=24,
        description="Shared secret used to validate candidate session JWTs.",
    )
    upstream_request_timeout_seconds: float = Field(
        default=10.0,
        ge=1.0,
        le=120.0,
        description="HTTP timeout for upstream service requests.",
    )

    @model_validator(mode="after")
    def require_secure_production_origins(self) -> "Settings":
        """Reject wildcard or non-HTTPS browser origins outside local use."""

        if self.app_env.lower() in {"development", "local", "test"}:
            return self
        invalid = [
            origin
            for origin in self.cors_origins
            if origin == "*" or not origin.startswith("https://")
        ]
        if invalid:
            raise ValueError("Production CORS origins must use explicit HTTPS URLs")
        local_secrets = {
            "INTERNAL_SERVICE_TOKEN": (
                self.internal_service_token,
                "change-me-local-internal-service-token",
            ),
            "CANDIDATE_SESSION_SECRET": (
                self.candidate_session_secret,
                "change-me-local-candidate-session-secret",
            ),
        }
        invalid_secrets = [
            name for name, (value, local_value) in local_secrets.items()
            if value == local_value
        ]
        if invalid_secrets:
            raise ValueError(
                "Production secrets must be configured: "
                + ", ".join(invalid_secrets)
            )
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
    def upstream_services(self) -> dict[str, str]:
        """Return configured upstream service base URLs keyed by service name."""

        return {
            "core": self.core_service_base_url,
            "code-execution": self.code_execution_service_base_url,
            "code-evaluation": self.code_evaluation_service_base_url,
        }


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for dependency injection."""

    return Settings()
