"""Authentication routes."""

from typing import Annotated

from fastapi import APIRouter, Depends

from api.rest.dependencies import get_current_user, settings_dependency
from config.settings import Settings
from schemas.auth import AuthenticatedUser, FirebaseWebConfig

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


@router.get(
    "/me",
    response_model=AuthenticatedUser,
    summary="Validate recruiter identity",
    description="Verifies a Firebase token and returns its active platform role.",
)
async def current_user(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> AuthenticatedUser:
    """Return the authenticated user for gateway authorization."""

    return user
