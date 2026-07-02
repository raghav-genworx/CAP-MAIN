"""Health check routes."""

from importlib import metadata
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from starlette.concurrency import run_in_threadpool

from api.rest.dependencies import settings_dependency
from config.settings import Settings
from data.database import database_is_ready
from schemas.health import HealthResponse

router = APIRouter(tags=["health"])


def _version() -> str:
    """Return installed package version."""

    try:
        return metadata.version("core-assessment-platform-service")
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
    response: Response,
) -> HealthResponse:
    """Return health status for this service."""

    ready = await run_in_threadpool(database_is_ready, settings)
    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        service=settings.app_name,
        environment=settings.app_env,
        status="ok" if ready else "degraded",
        version=_version(),
    )
