"""API gateway routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from api.rest.dependencies import gateway_service_dependency
from core.services.gateway.gateway_service import GatewayService
from schemas.gateway import GatewayHealthResponse, GatewayServiceCatalog

router = APIRouter(prefix="/gateway", tags=["gateway"])


@router.get(
    "/services",
    response_model=GatewayServiceCatalog,
    summary="List upstream platform services",
    description="Returns configured upstream service names and base URLs.",
)
async def list_services(
    service: Annotated[GatewayService, Depends(gateway_service_dependency)],
) -> GatewayServiceCatalog:
    """Return the gateway upstream service catalog."""

    return service.get_service_catalog()


@router.get(
    "/services/health",
    response_model=GatewayHealthResponse,
    summary="Check gateway upstream health",
    description="Checks gateway readiness and the health of configured services.",
)
async def upstream_health(
    service: Annotated[GatewayService, Depends(gateway_service_dependency)],
) -> GatewayHealthResponse:
    """Return health for the gateway and configured upstream services."""

    return await service.get_gateway_health()
