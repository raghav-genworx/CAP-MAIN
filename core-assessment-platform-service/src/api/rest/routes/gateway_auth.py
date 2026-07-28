"""Gateway authentication routes."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from api.rest.dependencies import gateway_service_dependency
from core.services.gateway.gateway_service import GatewayService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get(
    "/firebase-config",
    summary="Get Firebase web config through the gateway",
    description=(
        "Proxies the core platform Firebase browser configuration through the gateway."
    ),
)
async def firebase_config(
    service: Annotated[GatewayService, Depends(gateway_service_dependency)],
) -> dict[str, Any]:
    """Return Firebase web config from the core platform service."""

    return await service.get_core_firebase_config()
