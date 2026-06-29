"""API gateway upstream coordination."""

import asyncio
from typing import Any

import httpx

from config.settings import Settings
from core.exceptions.gateway import (
    UnknownUpstreamServiceError,
    UpstreamServiceUnavailableError,
)
from schemas.gateway import (
    GatewayHealthResponse,
    GatewayServiceCatalog,
    UpstreamService,
    UpstreamServiceHealth,
)

SERVICE_PURPOSES = {
    "core": (
        "Authentication config, recruiter workflows, candidate tokens, platform data"
    ),
    "code-execution": "Backend-only Judge0 code execution orchestration",
    "code-evaluation": "AI-assisted submission evaluation and reporting",
}


class GatewayService:
    """Coordinate public gateway requests to internal platform services."""

    def __init__(self, settings: Settings) -> None:
        """Initialize the service with runtime settings."""

        self._settings = settings

    def get_service_catalog(self) -> GatewayServiceCatalog:
        """Return registered upstream services."""

        return GatewayServiceCatalog(
            services=[
                UpstreamService(
                    name=name,
                    purpose=SERVICE_PURPOSES[name],
                )
                for name in self._settings.upstream_services
            ]
        )

    async def get_gateway_health(self) -> GatewayHealthResponse:
        """Return gateway status with best-effort upstream health checks."""

        upstreams = list(
            await asyncio.gather(
                *(
                    self.get_upstream_health(service_name)
                    for service_name in self._settings.upstream_services
                )
            )
        )
        gateway_status = (
            "ok"
            if all(upstream.status == "ok" for upstream in upstreams)
            else "degraded"
        )

        return GatewayHealthResponse(
            gateway_status=gateway_status,
            upstreams=upstreams,
        )

    async def get_upstream_health(self, service_name: str) -> UpstreamServiceHealth:
        """Return health for one configured upstream service."""

        base_url = self._get_base_url(service_name)
        health_url = f"{base_url}/api/v1/health"

        try:
            async with httpx.AsyncClient(
                timeout=self._settings.upstream_request_timeout_seconds
            ) as client:
                response = await client.get(health_url)
        except httpx.HTTPError:
            return UpstreamServiceHealth(
                name=service_name,
                status="unavailable",
                detail="Health check unavailable",
            )

        return UpstreamServiceHealth(
            name=service_name,
            status="ok" if response.is_success else "unhealthy",
            status_code=response.status_code,
            detail=None if response.is_success else "Upstream health check failed",
        )

    async def get_core_firebase_config(self) -> dict[str, Any]:
        """Proxy Firebase web config from the core platform service."""

        base_url = self._get_base_url("core")
        target_url = f"{base_url}/api/v1/auth/firebase-config"

        try:
            async with httpx.AsyncClient(
                timeout=self._settings.upstream_request_timeout_seconds
            ) as client:
                response = await client.get(target_url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamServiceUnavailableError("core") from exc

        data = response.json()
        if not isinstance(data, dict):
            raise UpstreamServiceUnavailableError("core")

        return data

    def _get_base_url(self, service_name: str) -> str:
        """Return a configured upstream service URL."""

        base_url = self._settings.upstream_services.get(service_name)
        if base_url is None:
            raise UnknownUpstreamServiceError(service_name)

        return base_url.rstrip("/")
