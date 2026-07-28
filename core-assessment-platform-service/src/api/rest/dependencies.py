"""Reusable FastAPI dependencies."""

from collections.abc import Awaitable, Callable, Generator
from secrets import compare_digest
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from config.settings import Settings, get_settings
from core.exceptions.auth import AuthenticationError, AuthorizationError
from core.exceptions.base import COEApplicationError
from core.services.assessments.assessment_service import AssessmentService
from core.services.auth.candidate_session_service import CandidateSessionService
from core.services.auth.gateway_auth_service import GatewayAuthService
from core.services.auth.role_service import RoleService
from core.services.evaluation.evaluation_service import (
    EvaluationService,
    get_evaluation_service,
)
from core.services.execution.code_execution_service import CodeExecutionService
from core.services.gateway.gateway_service import GatewayService
from core.services.notifications.notification_service import NotificationService
from core.services.question_bank.question_bank_service import QuestionBankService
from data.clients.postgres_client import session_dependency
from handlers.http_clients.firebase import FirebaseAuthService
from schemas.auth import AuthenticatedUser
from schemas.candidate_portal import CandidateSessionClaims
from schemas.roles import SubscriptionStatus, UserRole

security = HTTPBearer(auto_error=False)

internal_service_header = APIKeyHeader(
    name="X-Internal-Service-Token",
    auto_error=False,
)


def settings_dependency() -> Generator[Settings, None, None]:
    """Yield application settings for request handlers."""

    yield get_settings()


def require_internal_service(
    token: Annotated[str | None, Depends(internal_service_header)],
    settings: Annotated[Settings, Depends(settings_dependency)],
) -> None:
    """Authorize trusted service-to-service traffic.

    Guards the execution and evaluation routers, which are never reachable from a
    browser. Phase 4 deletes those routers, at which point this has no callers.
    """

    if token is None or not compare_digest(token, settings.internal_service_token):
        raise COEApplicationError("Unauthorized service request", status_code=401)


def code_execution_service_dependency() -> Generator[CodeExecutionService, None, None]:
    """Yield the Judge0-backed code execution service."""

    yield CodeExecutionService(get_settings())


def gateway_service_dependency() -> Generator[GatewayService, None, None]:
    """Yield the gateway upstream coordinator."""

    yield GatewayService(get_settings())


def gateway_auth_service_dependency() -> Generator[GatewayAuthService, None, None]:
    """Yield the gateway authorization service."""

    yield GatewayAuthService(get_settings())


def evaluation_service_dependency() -> Generator[EvaluationService, None, None]:
    """Yield the evaluation scoring and reporting service."""

    settings = get_settings()
    yield get_evaluation_service(
        settings.database_url,
        settings.evaluation_report_dir,
        settings.seed_demo_evaluations,
        settings.groq_api_key,
        settings.groq_base_url,
        settings.groq_model,
        settings.groq_request_timeout_seconds,
        settings.groq_retry_count,
        settings.groq_max_source_chars,
    )


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

    # Identity is always verified here, never taken from request headers.
    #
    # This used to accept X-User-Id / X-User-Email / X-User-Email-Verified whenever
    # X-Internal-Service-Token matched, because the gateway had already verified the
    # caller and was passing the result along. That made a single shared secret
    # sufficient to impersonate any recruiter. It existed only to save re-verifying
    # behind a trusted proxy; with the gateway folded in there is no proxy, and the
    # gateway forwarded the original Authorization header anyway, so nothing needs it.
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
        # 401, not 403. A missing credential is "unauthenticated", and it is also
        # what the browser has always seen here: the gateway rejected in
        # _bearer_token before core was reached. The candidate portal branches on
        # exactly this status -- CandidateAssessmentPage.tsx re-mints an expired
        # session from the stored invite token when a candidate request returns
        # 401, and rethrows on anything else. A 403 would turn a silent mid-exam
        # reconnect into a hard error. An invalid or expired token already answers
        # 401 via CandidateSessionError; this aligns the missing-token case.
        raise AuthenticationError("Missing candidate bearer token")
    return session_service.verify_session(credentials.credentials)
