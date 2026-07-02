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

    app_name: str = "Code Evaluation Service"
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
    database_url: str = Field(
        default=("postgresql+psycopg://cap_user:cap_password@localhost:55432/cap_core"),
        description=(
            "SQLAlchemy URL for shared CAP storage; evaluation uses its own schema."
        ),
    )
    evaluation_report_dir: str = Field(
        default="data/reports",
        description="Directory for generated evaluation report artifacts.",
    )
    seed_demo_evaluations: bool = Field(
        default=False,
        description="Explicit local-only opt-in for seeding demo evaluations.",
    )
    evaluation_worker_poll_interval_seconds: float = Field(
        default=5,
        ge=0.5,
        description="Seconds between queued evaluation worker polling cycles.",
    )
    evaluation_worker_batch_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum queued evaluation jobs processed per worker cycle.",
    )
    evaluation_retention_days: int = Field(
        default=365,
        ge=30,
        le=3650,
        description="Days to retain completed evaluation evidence and report files.",
    )
    evaluation_job_lease_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Seconds before an abandoned processing job can be reclaimed.",
    )
    groq_api_key: str = Field(
        default="",
        description="Groq API key used for AI code-quality evaluation.",
    )
    groq_base_url: str = Field(
        default="https://api.groq.com/openai/v1",
        description="Groq OpenAI-compatible API base URL.",
    )
    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        description="Groq model used for code-quality evaluation.",
    )
    groq_request_timeout_seconds: float = Field(default=60, ge=1, le=300)
    groq_retry_count: int = Field(default=3, ge=1, le=5)
    groq_max_source_chars: int = Field(default=80_000, ge=1_000, le=200_000)

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
        if (
            self.app_env.lower() not in {"development", "local", "test"}
            and self.seed_demo_evaluations
        ):
            raise ValueError("Demo evaluation seeding is allowed only for local use")
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
