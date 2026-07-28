"""API gateway upstream coordination."""

import asyncio
from collections.abc import Mapping
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

HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class GatewayService:
    """Coordinate public gateway requests to internal platform services."""

    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Initialize the service with runtime settings."""

        self._settings = settings
        self._transport = transport

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
                timeout=self._settings.upstream_request_timeout_seconds,
                transport=self._transport,
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

        if self._settings.firebase_project_id:
            return {
                "apiKey": self._settings.firebase_api_key,
                "authDomain": self._settings.firebase_auth_domain,
                "projectId": self._settings.firebase_project_id,
                "appId": self._settings.firebase_app_id,
                "storageBucket": None,
                "messagingSenderId": None,
                "measurementId": None,
            }

        base_url = self._get_base_url("core")
        target_url = f"{base_url}/api/v1/auth/firebase-config"

        try:
            async with httpx.AsyncClient(
                timeout=self._settings.upstream_request_timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.get(target_url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise UpstreamServiceUnavailableError("core") from exc

        data = response.json()
        if not isinstance(data, dict):
            raise UpstreamServiceUnavailableError("core")

        return data

    async def open_proxy_response(
        self,
        *,
        service_name: str,
        path: str,
        method: str,
        query: str,
        headers: Mapping[str, str],
        body: bytes,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[httpx.AsyncClient, httpx.Response]:
        """Open a streaming request to an approved upstream service."""

        base_url = self._get_base_url(service_name)
        target_url = f"{base_url}/api/v1/{path.lstrip('/')}"
        if query:
            target_url = f"{target_url}?{query}"

        upstream_headers = self._forward_request_headers(headers)
        if service_name in {"code-execution", "code-evaluation"}:
            upstream_headers["X-Internal-Service-Token"] = (
                self._settings.internal_service_token
            )
        if extra_headers:
            upstream_headers.update(extra_headers)

        client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                self._settings.upstream_request_timeout_seconds,
                read=None,
            ),
            transport=self._transport,
        )
        request = client.build_request(
            method=method,
            url=target_url,
            headers=upstream_headers,
            content=body,
        )
        try:
            response = await client.send(request, stream=True)
        except httpx.HTTPError as exc:
            await client.aclose()
            raise UpstreamServiceUnavailableError(service_name) from exc
        return client, response

    @staticmethod
    def response_headers(headers: httpx.Headers) -> dict[str, str]:
        """Return end-to-end response headers safe to relay to a browser."""

        return {
            key: value
            for key, value in headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS
        }

    @staticmethod
    async def close_proxy_response(
        client: httpx.AsyncClient,
        response: httpx.Response,
    ) -> None:
        """Release an upstream response and its client after streaming."""

        await response.aclose()
        await client.aclose()

    @staticmethod
    def _forward_request_headers(headers: Mapping[str, str]) -> dict[str, str]:
        """Drop connection-specific and privileged browser request headers."""

        blocked = HOP_BY_HOP_HEADERS | {
            "content-length",
            "host",
            "x-internal-service-token",
        }
        return {
            key: value for key, value in headers.items() if key.lower() not in blocked
        }

    def _get_base_url(self, service_name: str) -> str:
        """Return a configured upstream service URL."""

        base_url = self._settings.upstream_services.get(service_name)
        if base_url is None:
            raise UnknownUpstreamServiceError(service_name)

        return base_url.rstrip("/")
