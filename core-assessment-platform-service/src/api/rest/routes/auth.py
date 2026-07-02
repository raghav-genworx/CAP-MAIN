"""Authentication routes."""

from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from api.rest.dependencies import (
    get_current_user,
    get_role_service,
    settings_dependency,
)
from config.settings import Settings
from core.services.role_service import RoleService
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


@router.post(
    "/start-free-trial",
    response_model=AuthenticatedUser,
    summary="Start recruiter free trial",
    description="Activates the current recruiter's no-charge subscription.",
)
async def start_free_trial(
    user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    role_service: Annotated[RoleService, Depends(get_role_service)],
) -> AuthenticatedUser:
    """Complete subscription onboarding for the authenticated recruiter."""

    role = await run_in_threadpool(role_service.start_free_trial, user.uid)
    return user.model_copy(
        update={
            "subscription_status": role.subscription_status,
            "trial_started_at": role.trial_started_at,
        }
    )
