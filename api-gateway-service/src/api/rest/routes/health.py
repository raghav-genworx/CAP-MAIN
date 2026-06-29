"""Health check routes."""

from importlib import metadata
from typing import Annotated

from fastapi import APIRouter, Depends

from api.rest.dependencies import settings_dependency
from config.settings import Settings
from schemas.health import HealthResponse

router = APIRouter(tags=["health"])


def _version() -> str:
    """Return installed package version."""

    try:
        return metadata.version("api-gateway-service")
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
) -> HealthResponse:
    """Return health status for this service."""

    return HealthResponse(
        service=settings.app_name,
        environment=settings.app_env,
        status="ok",
        version=_version(),
    )
