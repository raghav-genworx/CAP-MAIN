"""Reusable FastAPI dependencies."""

from collections.abc import Awaitable, Callable, Generator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from config.settings import Settings, get_settings
from core.exceptions.auth import AuthorizationError
from core.services.assessment_service import AssessmentService
from core.services.candidate_session_service import CandidateSessionService
from core.services.notification_service import NotificationService
from core.services.question_bank_service import QuestionBankService
from core.services.role_service import RoleService
from data.clients.database import session_dependency
from handlers.http_clients.firebase import FirebaseAuthService
from schemas.auth import AuthenticatedUser, FirebaseIdentity
from schemas.candidate_portal import CandidateSessionClaims
from schemas.roles import SubscriptionStatus, UserRole

security = HTTPBearer(auto_error=False)


def settings_dependency() -> Generator[Settings, None, None]:
    """Yield application settings for request handlers."""

    yield get_settings()


def database_session_dependency(
    settings: Annotated[Settings, Depends(settings_dependency)],
) -> Generator[Session, None, None]:
    """Yield a request-scoped PostgreSQL session."""

    yield from session_dependency(settings)


def get_firebase_auth_service(
    settings: Annotated[Settings, Depends(settings_dependency)],
) -> FirebaseAuthService:
    """Return the Firebase auth service."""

    return FirebaseAuthService(settings)


def get_role_service(
    settings: Annotated[Settings, Depends(settings_dependency)],
    session: Annotated[Session, Depends(database_session_dependency)],
) -> RoleService:
    """Return the PostgreSQL-backed role service."""

    return RoleService(settings, session)


def get_question_bank_service(
    session: Annotated[Session, Depends(database_session_dependency)],
) -> QuestionBankService:
    """Return the question bank service."""

    return QuestionBankService(session)


def get_assessment_service(
    session: Annotated[Session, Depends(database_session_dependency)],
    settings: Annotated[Settings, Depends(settings_dependency)],
) -> AssessmentService:
    """Return the assessment orchestration service."""

    return AssessmentService(session, settings)


def get_notification_service(
    session: Annotated[Session, Depends(database_session_dependency)],
    settings: Annotated[Settings, Depends(settings_dependency)],
) -> NotificationService:
    """Return the recruiter notification service."""

    return NotificationService(session, settings)


def get_candidate_session_service(
    settings: Annotated[Settings, Depends(settings_dependency)],
) -> CandidateSessionService:
    """Return the candidate session JWT service."""

    return CandidateSessionService(settings)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    auth_service: Annotated[
        FirebaseAuthService,
        Depends(get_firebase_auth_service),
    ],
    role_service: Annotated[RoleService, Depends(get_role_service)],
    settings: Annotated[Settings, Depends(settings_dependency)],
) -> AuthenticatedUser:
    """Verify the Firebase token and attach the platform role."""

    internal_token = request.headers.get("x-internal-service-token")
    user_id = request.headers.get("x-user-id")

    if internal_token and internal_token == settings.internal_service_token and user_id:
        email = request.headers.get("x-user-email")
        name = request.headers.get("x-user-name")
        picture = request.headers.get("x-user-picture")
        email_verified_str = request.headers.get("x-user-email-verified")
        email_verified = (
            email_verified_str.lower() == "true" if email_verified_str else False
        )

        identity = FirebaseIdentity(
            uid=user_id,
            email=email if email else None,
            name=name if name else None,
            picture=picture if picture else None,
            email_verified=email_verified,
        )
    else:
        identity = await run_in_threadpool(auth_service.verify_credentials, credentials)

    return await run_in_threadpool(role_service.resolve_user, identity)


def require_role(
    required_role: UserRole,
) -> Callable[..., Awaitable[AuthenticatedUser]]:
    """Require a specific platform role for a route dependency."""

    async def dependency(
        current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        if current_user.role != required_role:
            raise AuthorizationError("Insufficient platform role")
        if (
            required_role == UserRole.RECRUITER
            and current_user.subscription_status != SubscriptionStatus.FREE_TRIAL
        ):
            raise AuthorizationError("Start your free trial to access recruiter tools")

        return current_user

    return dependency


async def get_current_candidate_session(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    session_service: Annotated[
        CandidateSessionService,
        Depends(get_candidate_session_service),
    ],
) -> CandidateSessionClaims:
    """Verify a bearer token as a candidate portal session."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthorizationError("Missing candidate bearer token")
    return session_service.verify_session(credentials.credentials)
