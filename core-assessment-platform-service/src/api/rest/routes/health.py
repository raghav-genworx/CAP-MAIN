"""Health check routes.

All four applications served from this codebase expose ``GET /health`` with the same
payload but a different readiness probe: core and evaluation check PostgreSQL,
execution checks Judge0, and the gateway reports statically. Rather than keep four
near-identical modules, the router is built per application and the probe injected.
"""

from collections.abc import Awaitable, Callable
from importlib import metadata
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from starlette.concurrency import run_in_threadpool

from api.rest.dependencies import settings_dependency
from config.settings import Settings
from data.clients.postgres_client import database_is_ready
from schemas.health import HealthResponse

#: Returns whether the application's critical dependency is reachable.
ReadinessProbe = Callable[[Settings], Awaitable[bool]]


async def always_ready(settings: Settings) -> bool:
    """Report ready unconditionally, for an application with no hard dependency."""

    return True


async def postgres_ready(settings: Settings) -> bool:
    """Report whether PostgreSQL accepts a lightweight query."""

    return await run_in_threadpool(database_is_ready, settings)


def _version(distribution: str) -> str:
    """Return the installed package version, or a default when not installed."""

    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "0.1.0"


def build_health_router(
    *,
    distribution: str = "core-assessment-platform-service",
    probe: ReadinessProbe = postgres_ready,
) -> APIRouter:
    """Return a health router reporting readiness through ``probe``.

    A failing probe answers 503 with ``status="degraded"``; Compose and Cloud Run
    both treat that as unhealthy.
    """

    router = APIRouter(tags=["health"])

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

        ready = await probe(settings)
        if not ready:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            service=settings.app_name,
            environment=settings.app_env,
            status="ok" if ready else "degraded",
            version=_version(distribution),
        )

    return router


#: The core application's router, preserving the previous module-level attribute.
router = build_health_router()
