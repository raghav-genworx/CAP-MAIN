"""Health endpoint schemas."""

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Health check response payload."""

    model_config = ConfigDict(frozen=True)

    service: str
    environment: str
    status: str
    version: str
