"""Reusable FastAPI dependencies."""

from collections.abc import Generator
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends
from fastapi.security import APIKeyHeader

from config.settings import Settings, get_settings
from core.exceptions.base import COEApplicationError
from core.services.code_execution_service import CodeExecutionService

internal_service_header = APIKeyHeader(
    name="X-Internal-Service-Token",
    auto_error=False,
)


def settings_dependency() -> Generator[Settings, None, None]:
    """Yield application settings for request handlers."""

    yield get_settings()


def code_execution_service_dependency() -> Generator[CodeExecutionService, None, None]:
    """Yield the code execution business service."""

    yield CodeExecutionService(get_settings())


def require_internal_service(
    token: Annotated[str | None, Depends(internal_service_header)],
    settings: Annotated[Settings, Depends(settings_dependency)],
) -> None:
    """Authorize trusted service-to-service execution traffic."""

    if token is None or not compare_digest(token, settings.internal_service_token):
        raise COEApplicationError("Unauthorized service request", status_code=401)
