"""Reusable FastAPI dependencies."""

from collections.abc import Generator
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends
from fastapi.security import APIKeyHeader

from config.settings import Settings, get_settings
from core.exceptions.base import COEApplicationError
from core.services.evaluation_service import EvaluationService, get_evaluation_service

internal_service_header = APIKeyHeader(
    name="X-Internal-Service-Token",
    auto_error=False,
)


def settings_dependency() -> Generator[Settings, None, None]:
    """Yield application settings for request handlers."""

    yield get_settings()


def evaluation_service_dependency() -> Generator[EvaluationService, None, None]:
    """Yield the code evaluation business service."""

    settings = get_settings()
    yield get_evaluation_service(
        settings.database_url,
        settings.evaluation_report_dir,
        settings.seed_demo_evaluations,
        settings.groq_api_key,
        settings.groq_base_url,
        settings.groq_model,
        settings.groq_request_timeout_seconds,
        settings.groq_retry_count,
        settings.groq_max_source_chars,
    )


def require_internal_service(
    token: Annotated[str | None, Depends(internal_service_header)],
    settings: Annotated[Settings, Depends(settings_dependency)],
) -> None:
    """Authorize trusted service-to-service evaluation traffic."""

    if token is None or not compare_digest(token, settings.internal_service_token):
        raise COEApplicationError("Unauthorized service request", status_code=401)
