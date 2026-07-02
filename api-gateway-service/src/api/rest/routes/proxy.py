"""Authenticated reverse-proxy routes for browser API traffic."""

from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from api.rest.dependencies import (
    gateway_auth_service_dependency,
    gateway_service_dependency,
)
from core.services.gateway_auth_service import GatewayAuthService
from core.services.gateway_service import GatewayService

router = APIRouter(tags=["proxy"])


def _is_event_stream(upstream_content_type: str | None) -> bool:
    """Return whether an upstream response is a server-sent event stream."""

    return bool(
        upstream_content_type
        and upstream_content_type.lower().startswith("text/event-stream")
    )


def _proxy_media_type(upstream_content_type: str | None) -> str | None:
    """Return the media type FastAPI should use for the proxied response."""

    if _is_event_stream(upstream_content_type):
        return "text/event-stream"
    return upstream_content_type


def _proxy_headers(
    gateway_service: GatewayService,
    upstream_content_type: str | None,
    upstream_headers: httpx.Headers,
) -> dict[str, str]:
    """Return browser-safe headers for a proxied response."""

    headers = gateway_service.response_headers(upstream_headers)
    if _is_event_stream(upstream_content_type):
        headers["Cache-Control"] = "no-cache, no-transform"
        headers["X-Accel-Buffering"] = "no"
    return headers


async def _relay_upstream_stream(
    gateway_service: GatewayService,
    client: httpx.AsyncClient,
    upstream: httpx.Response,
) -> AsyncIterator[bytes]:
    """Relay upstream bytes and close resources when streaming finishes."""

    try:
        async for chunk in upstream.aiter_raw():
            if chunk:
                yield chunk
    finally:
        await gateway_service.close_proxy_response(client, upstream)


@router.api_route(
    "/{service_name}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
    summary="Authorize and proxy a browser API request",
    description=(
        "Validates browser credentials and proxies approved traffic to a registered "
        "internal service."
    ),
)
async def proxy_request(
    service_name: str,
    path: str,
    request: Request,
    auth_service: Annotated[
        GatewayAuthService,
        Depends(gateway_auth_service_dependency),
    ],
    gateway_service: Annotated[
        GatewayService,
        Depends(gateway_service_dependency),
    ],
) -> StreamingResponse:
    """Authorize one request and relay its response without buffering."""

    authorization = request.headers.get("authorization")
    await auth_service.authorize(
        service_name=service_name,
        path=path,
        method=request.method,
        authorization=authorization,
    )
    client, upstream = await gateway_service.open_proxy_response(
        service_name=service_name,
        path=path,
        method=request.method,
        query=request.url.query,
        headers=request.headers,
        body=await request.body(),
    )
    upstream_content_type = upstream.headers.get("content-type")
    return StreamingResponse(
        _relay_upstream_stream(gateway_service, client, upstream),
        status_code=upstream.status_code,
        headers=_proxy_headers(
            gateway_service,
            upstream_content_type,
            upstream.headers,
        ),
        media_type=_proxy_media_type(upstream_content_type),
    )
