"""Health check routes."""

from importlib import metadata
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from api.rest.dependencies import (
    code_execution_service_dependency,
    settings_dependency,
)
from config.settings import Settings
from core.exceptions.execution import Judge0ServiceError
from core.services.code_execution_service import CodeExecutionService
from schemas.health import HealthResponse

router = APIRouter(tags=["health"])


def _version() -> str:
    """Return installed package version."""

    try:
        return metadata.version("code-execution-service")
    except metadata.PackageNotFoundError:
        return "0.1.0"


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Check service health",
    description="Returns service metadata and readiness status.",
)
async def health(
    settings: Annotated[Settings, Depends(settings_dependency)],
    service: Annotated[
        CodeExecutionService,
        Depends(code_execution_service_dependency),
    ],
    response: Response,
) -> HealthResponse:
    """Return health status for this service."""

    try:
        ready = bool(await service.get_languages())
    except Judge0ServiceError:
        ready = False
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        service=settings.app_name,
        environment=settings.app_env,
        status="ok" if ready else "degraded",
        version=_version(),
    )
