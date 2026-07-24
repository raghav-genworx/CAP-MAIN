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

    app_name: str = "Code Execution Service"
    app_env: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    internal_service_token: str = Field(
        default="change-me-local-internal-service-token",
        min_length=24,
        description="Shared token accepted only from trusted platform services.",
    )
    cors_allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        description="Comma-separated list of allowed CORS origins.",
    )
    judge0_base_url: str = Field(
        default="http://localhost:2358",
        description="Base URL for the self-hosted Judge0 API.",
    )
    judge0_api_key: str | None = Field(
        default=None,
        description="Optional API key for secured Judge0 deployments.",
    )
    judge0_auth_header: str = Field(
        default="X-Auth-Token",
        description="Header used to send the optional Judge0 API key.",
    )
    judge0_request_timeout_seconds: float = Field(
        default=10.0,
        description="HTTP timeout for Judge0 API requests.",
    )
    judge0_poll_interval_seconds: float = Field(
        default=0.5,
        description="Delay between Judge0 submission status checks.",
    )
    judge0_max_poll_attempts: int = Field(
        default=30,
        description="Maximum number of Judge0 status checks before timing out.",
    )
    default_cpu_time_limit_seconds: float = Field(
        default=2.0,
        description="Default CPU time limit sent to Judge0 submissions.",
    )
    max_output_characters: int = Field(
        default=50_000,
        ge=1_000,
        le=1_000_000,
        description="Maximum characters retained for each execution output field.",
    )
    judge0_poll_margin_seconds: float = Field(
        default=5.0,
        ge=1.0,
        le=60.0,
        description="Extra polling time beyond the submitted CPU limit.",
    )
    default_memory_limit_kb: int = Field(
        default=128000,
        description="Default memory limit sent to Judge0 submissions.",
    )
    java_minimum_memory_limit_kb: int = Field(
        default=512000,
        ge=256000,
        le=512000,
        description=(
            "Minimum Java sandbox memory, including JVM heap and runtime overhead."
        ),
    )

    @model_validator(mode="after")
    def require_production_service_token(self) -> "Settings":
        """Prevent deployment with the documented local-only token."""

        if (
            self.app_env.lower() not in {"development", "local", "test"}
            and self.internal_service_token == "change-me-local-internal-service-token"
        ):
            raise ValueError("INTERNAL_SERVICE_TOKEN must be set outside local use")
        invalid_origins = [
            origin
            for origin in self.cors_origins
            if origin == "*" or not origin.startswith("https://")
        ]
        if self.app_env.lower() not in {"development", "local", "test"} and (
            invalid_origins
        ):
            raise ValueError("Production CORS origins must use explicit HTTPS URLs")
        return self

    @property
    def cors_origins(self) -> list[str]:
        """Return configured CORS origins as a normalized list."""

        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for dependency injection."""

    return Settings()
