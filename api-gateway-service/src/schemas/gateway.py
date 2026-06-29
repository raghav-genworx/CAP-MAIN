"""Gateway response schemas."""

from pydantic import BaseModel


class UpstreamService(BaseModel):
    """Configured upstream service metadata."""

    name: str
    purpose: str


class UpstreamServiceHealth(BaseModel):
    """Health snapshot for one upstream service."""

    name: str
    status: str
    status_code: int | None = None
    detail: str | None = None


class GatewayServiceCatalog(BaseModel):
    """List of services reachable through the gateway."""

    services: list[UpstreamService]


class GatewayHealthResponse(BaseModel):
    """Gateway and upstream health response."""

    gateway_status: str
    upstreams: list[UpstreamServiceHealth]
