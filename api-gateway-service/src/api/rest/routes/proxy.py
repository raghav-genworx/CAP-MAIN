"""Authenticated reverse-proxy routes for browser API traffic."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from api.rest.dependencies import (
    gateway_auth_service_dependency,
    gateway_service_dependency,
)
from core.services.gateway_auth_service import GatewayAuthService
from core.services.gateway_service import GatewayService

router = APIRouter(tags=["proxy"])


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
    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        headers=gateway_service.response_headers(upstream.headers),
        background=BackgroundTask(
            gateway_service.close_proxy_response,
            client,
            upstream,
        ),
    )
