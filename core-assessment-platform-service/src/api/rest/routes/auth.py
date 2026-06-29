"""Authentication routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from api.rest.dependencies import settings_dependency
from config.settings import Settings
from schemas.auth import FirebaseWebConfig

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get(
    "/firebase-config",
    response_model=FirebaseWebConfig,
    summary="Get Firebase web config",
    description="Returns Firebase browser SDK settings from environment config.",
)
async def firebase_config(
    settings: Annotated[Settings, Depends(settings_dependency)],
) -> FirebaseWebConfig:
    """Return Firebase settings needed by the browser SDK."""

    return settings.firebase_web_config
