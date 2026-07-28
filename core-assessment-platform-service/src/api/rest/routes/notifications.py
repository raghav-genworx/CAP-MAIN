"""Recruiter notification preference and inbox routes."""

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from api.rest.dependencies import (
    database_session_dependency,
    get_notification_service,
    require_role,
    settings_dependency,
)
from api.rest.routes import sse
from config.settings import Settings
from core.services.notifications.notification_service import NotificationService
from data.clients.redis_client import NotificationBroker
from schemas.auth import AuthenticatedUser
from schemas.notifications import (
    MarkReadResponse,
    NotificationListResponse,
    NotificationSettingsRecord,
    NotificationSettingsUpdateRequest,
    UnreadCountResponse,
)
from schemas.roles import UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

_POLL_FALLBACK_SECONDS = 5.0


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List recruiter notifications",
    description="Returns the recruiter dashboard notification inbox.",
)
async def list_notifications(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[NotificationService, Depends(get_notification_service)],
    unread_only: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> NotificationListResponse:
    return await run_in_threadpool(
        service.list_notifications,
        current_user.uid,
        limit=limit,
        unread_only=unread_only,
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    summary="Unread notification count",
    description="Returns the number of unread recruiter notifications.",
)
async def unread_count(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> UnreadCountResponse:
    return await run_in_threadpool(service.unread_count, current_user.uid)


@router.get(
    "/stream",
    summary="Stream recruiter notifications",
    description="Streams recruiter dashboard notifications as server-sent events.",
)
async def stream_notifications(
    request: Request,
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[NotificationService, Depends(get_notification_service)],
    settings: Annotated[Settings, Depends(settings_dependency)],
    session: Annotated[Session, Depends(database_session_dependency)],
) -> StreamingResponse:
    recruiter_uid = current_user.uid
    broker = NotificationBroker(settings)
    try:
        initial_payload = await run_in_threadpool(
            service.stream_snapshot,
            recruiter_uid,
        )
    finally:
        await run_in_threadpool(session.close)
    # Streaming responses keep request dependencies alive. Return the database
    # connection to the pool between snapshots instead of pinning it for the
    # lifetime of the browser's SSE connection.

    async def signal_source() -> AsyncIterator[str]:
        """Yield refresh signals from Redis, falling back to DB polling."""

        try:
            async for signal in broker.listen(
                recruiter_uid,
                heartbeat_seconds=settings.notification_stream_heartbeat_seconds,
            ):
                yield signal
        except Exception:
            logger.warning(
                "Notification Redis stream unavailable; falling back to polling",
                exc_info=True,
            )
            while True:
                await asyncio.sleep(_POLL_FALLBACK_SECONDS)
                yield "message"

    async def notification_events() -> AsyncIterator[str]:
        last_payload = initial_payload.model_dump_json()
        yield f"event: notifications\ndata: {last_payload}\n\n"

        try:
            async for signal in signal_source():
                if await request.is_disconnected():
                    break
                if signal == "message":
                    try:
                        payload = await run_in_threadpool(
                            service.stream_snapshot,
                            recruiter_uid,
                        )
                    finally:
                        await run_in_threadpool(session.close)
                    serialized = payload.model_dump_json()
                    if serialized != last_payload:
                        last_payload = serialized
                        yield f"event: notifications\ndata: {serialized}\n\n"
                        continue
                yield "event: heartbeat\ndata: {}\n\n"
        finally:
            await run_in_threadpool(session.close)

    return sse.event_stream(notification_events())


@router.post(
    "/read-all",
    response_model=MarkReadResponse,
    summary="Mark all notifications read",
    description="Marks every unread recruiter notification as read.",
)
async def mark_all_read(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> MarkReadResponse:
    return await run_in_threadpool(service.mark_all_read, current_user.uid)


@router.post(
    "/{notification_id}/read",
    response_model=MarkReadResponse,
    summary="Mark a notification read",
    description="Marks one recruiter notification as read.",
)
async def mark_read(
    notification_id: str,
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> MarkReadResponse:
    return await run_in_threadpool(service.mark_read, current_user.uid, notification_id)


@router.get(
    "/settings",
    response_model=NotificationSettingsRecord,
    summary="Get notification preferences",
    description="Returns the recruiter's notification preferences.",
)
async def get_settings(
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> NotificationSettingsRecord:
    return await run_in_threadpool(service.get_settings, current_user.uid)


@router.put(
    "/settings",
    response_model=NotificationSettingsRecord,
    summary="Update notification preferences",
    description="Updates the recruiter's notification preferences.",
)
async def update_settings(
    payload: NotificationSettingsUpdateRequest,
    current_user: Annotated[
        AuthenticatedUser,
        Depends(require_role(UserRole.RECRUITER)),
    ],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> NotificationSettingsRecord:
    return await run_in_threadpool(service.update_settings, current_user.uid, payload)
