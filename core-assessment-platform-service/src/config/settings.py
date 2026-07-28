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
    log_json: bool = Field(
        default=False,
        description=(
            "Emit one JSON object per log line. Enabled in deployments so the "
            "log platform can index fields; off locally for readability."
        ),
    )
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
    groq_api_key_1: str = Field(
        default="",
        validation_alias=AliasChoices("GROQ_API_KEY_1"),
    )
    groq_api_key_2: str = Field(
        default="",
        validation_alias=AliasChoices("GROQ_API_KEY_2"),
    )
    groq_api_key_3: str = Field(
        default="",
        validation_alias=AliasChoices("GROQ_API_KEY_3"),
    )
    groq_api_key_4: str = Field(
        default="",
        validation_alias=AliasChoices("GROQ_API_KEY_4"),
    )
    groq_base_url: str = Field(
        default="https://api.groq.com/openai/v1",
        validation_alias=AliasChoices("GROQ_BASE_URL", "VITE_GROQ_BASE_URL"),
    )
    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        validation_alias=AliasChoices("GROQ_MODEL", "VITE_GROQ_MODEL"),
    )
    groq_gpt_oss_model: str = Field(
        default="openai/gpt-oss-120b",
        validation_alias=AliasChoices("GROQ_GPT_OSS_MODEL"),
    )
    groq_retry_count: int = 3
    groq_retry_backoff_seconds: float = 0.5
    groq_request_timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    langsmith_tracing: bool = Field(
        default=False,
        validation_alias=AliasChoices("LANGSMITH_TRACING", "LANGCHAIN_TRACING"),
    )
    langsmith_endpoint: str = Field(
        default="https://api.smith.langchain.com",
        validation_alias=AliasChoices("LANGSMITH_ENDPOINT", "LANGCHAIN_ENDPOINT"),
    )
    langsmith_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"),
    )
    langsmith_project: str = Field(
        default="CAP",
        validation_alias=AliasChoices("LANGSMITH_PROJECT", "LANGCHAIN_PROJECT"),
    )
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

    # --- Internal transports ---------------------------------------------------
    # How this process reaches the execution and evaluation contexts. "http" keeps
    # the original service-to-service call; "inprocess" calls the service directly.
    # Flipping back is an environment change with no redeploy, which is the
    # rollback lever for the consolidation.
    execution_transport: str = Field(
        default="http",
        pattern="^(http|inprocess)$",
        description="Transport used to reach code execution: http | inprocess.",
    )
    evaluation_transport: str = Field(
        default="http",
        pattern="^(http|inprocess)$",
        description="Transport used to reach code evaluation: http | inprocess.",
    )

    # --- Judge0 sandbox (merged from code-execution-service) -------------------
    # Candidate code is never executed in this process; these configure the HTTP
    # adapter that submits to an isolated Judge0 deployment.
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
    judge0_poll_margin_seconds: float = Field(
        default=5.0,
        ge=1.0,
        le=60.0,
        description="Extra polling time beyond the submitted CPU limit.",
    )
    default_cpu_time_limit_seconds: float = Field(
        default=2.0,
        description="Default CPU time limit sent to Judge0 submissions.",
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
    max_output_characters: int = Field(
        default=50_000,
        ge=1_000,
        le=1_000_000,
        description="Maximum characters retained for each execution output field.",
    )

    # --- Evaluation (merged from code-evaluation-service) ----------------------
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
    groq_max_source_chars: int = Field(default=80_000, ge=1_000, le=200_000)

    # --- Edge gateway (merged from api-gateway-service) -----------------------
    # Upstream URLs the proxy forwards to. Phase 5 folds the gateway into the core
    # application and these become unused.
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
    upstream_request_timeout_seconds: float = Field(
        default=10.0,
        ge=1.0,
        le=120.0,
        description="HTTP timeout for upstream service requests.",
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
    # --- Redis -----------------------------------------------------------------
    # Three distinct URLs, deliberately not aliased onto one another.
    #
    # `redis_url` previously also accepted CELERY_BROKER_URL. Compose sets the two
    # Celery variables for every service but REDIS_URL only for core, so in the
    # other four containers the notification pub/sub URL silently resolved to the
    # Celery broker. Harmless while both point at db 0 and nothing reads it, but it
    # becomes a live misrouting the moment the broker moves to its own database or
    # instance -- which is exactly what Phase 6 does.
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("REDIS_URL"),
        description="Redis connection URL for notification pub/sub push.",
    )
    celery_broker_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("CELERY_BROKER_URL"),
        description="Redis connection URL Celery dispatches tasks through.",
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/1",
        validation_alias=AliasChoices("CELERY_RESULT_BACKEND"),
        description="Redis connection URL Celery stores task results in.",
    )
    celery_beat_schedule_path: str = Field(
        default="celerybeat-schedule",
        description=(
            "Where beat persists its schedule. It shelves to the working "
            "directory by default, which is not writable by the non-root "
            "container user -- beat then dies while the worker still reports "
            "ready, silently stopping the sweep. Point it at a writable path."
        ),
    )
    notification_channel_prefix: str = Field(
        default="notifications",
        description="Redis channel prefix for recruiter notification events.",
    )
    notification_stream_heartbeat_seconds: float = Field(
        default=20.0,
        ge=1.0,
        le=120.0,
        description="Idle heartbeat interval for the notification SSE stream.",
    )

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
        # Carried over from the evaluation service's own validator. Seeding writes
        # fabricated scorecards into the evaluation tables, which must never happen
        # against a real deployment.
        if self.seed_demo_evaluations:
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

    @property
    def upstream_services(self) -> dict[str, str]:
        """Return upstream base URLs the gateway will proxy a browser request to.

        Only ``core``. Execution and evaluation were reachable here too, and the
        gateway *injected* the internal service token on the way through -- so any
        recruiter with an active trial could drive Judge0 or read evaluation data
        directly. No frontend code ever used those paths (see
        ``docs/api/contract-inventory.md``), so removing them closes the hole
        without touching the browser contract.

        This is deliberately not the same thing as deleting the execution and
        evaluation routers. Those still serve the internal HTTP transport, which is
        what ``EXECUTION_TRANSPORT=http`` falls back to. They go away in Phase 6
        together with the separate containers, once in-process needs no rollback.
        """

        return {"core": self.core_service_base_url}

    @property
    def groq_api_keys(self) -> list[str]:
        """Return configured Groq key slots in failover order."""

        return [api_key for _, api_key in self.groq_api_key_slots]

    @property
    def groq_api_key_slots(self) -> list[tuple[int, str]]:
        """Return configured Groq key slots with stable slot numbers."""

        first_slot = self.groq_api_key_1.strip() or self.groq_api_key.strip()
        candidates = [
            (1, first_slot),
            (2, self.groq_api_key_2),
            (3, self.groq_api_key_3),
            (4, self.groq_api_key_4),
        ]
        keys: list[tuple[int, str]] = []
        seen: set[str] = set()
        for slot_number, candidate in candidates:
            normalized = candidate.strip()
            if normalized and normalized not in seen:
                keys.append((slot_number, normalized))
                seen.add(normalized)
        return keys

    @property
    def groq_fallback_models(self) -> list[str]:
        """Return GPT-OSS then Llama 70B in failover order."""

        models = [
            self.groq_gpt_oss_model.strip(),
            self.groq_model.strip(),
        ]
        return list(dict.fromkeys(model for model in models if model))

    @property
    def ai_model_sequence_label(self) -> str:
        """Return a human-readable AI failover sequence label."""

        labels = [
            *(f"groq:{model}" for model in self.groq_fallback_models),
        ]
        return " -> ".join(labels)

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
