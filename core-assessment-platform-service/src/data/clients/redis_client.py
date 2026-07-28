"""Redis pub/sub broker for pushing recruiter notification events.

The submission/evaluation flow publishes a lightweight ping per recruiter after
its database transaction commits; the notification SSE endpoint subscribes to
that recruiter's channel and refreshes the client the moment an event arrives,
avoiding server-side database polling.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from functools import lru_cache
from typing import Any, cast

import redis
import redis.asyncio as aioredis

from config.settings import Settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def _sync_pool(redis_url: str) -> redis.ConnectionPool:
    """Return a cached synchronous connection pool for publishing."""

    return redis.ConnectionPool.from_url(redis_url)


class NotificationBroker:
    """Publish and subscribe to per-recruiter notification channels."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._prefix = settings.notification_channel_prefix

    def _channel(self, recruiter_uid: str) -> str:
        return f"{self._prefix}:{recruiter_uid}"

    def publish(self, recruiter_uid: str) -> None:
        """Best-effort publish of a refresh ping for a recruiter.

        Failures are swallowed so notification delivery can never break the
        candidate submission or evaluation flow.
        """

        try:
            client = redis.Redis(connection_pool=_sync_pool(self._settings.redis_url))
            client.publish(self._channel(recruiter_uid), "1")
        except Exception:
            logger.warning(
                "Failed to publish notification event for %s",
                recruiter_uid,
                exc_info=True,
            )

    async def listen(
        self,
        recruiter_uid: str,
        *,
        heartbeat_seconds: float,
    ) -> AsyncIterator[str]:
        """Yield ``"message"`` on each event and ``"heartbeat"`` on idle timeout.

        Raises if the Redis connection cannot be established so the caller can
        fall back to database polling.
        """

        client = aioredis.from_url(self._settings.redis_url)
        pubsub = client.pubsub()
        channel = self._channel(recruiter_uid)
        await pubsub.subscribe(channel)
        try:
            while True:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=heartbeat_seconds,
                )
                yield "heartbeat" if message is None else "message"
        finally:
            with suppress(Exception):
                await pubsub.unsubscribe(channel)
                await cast(Any, pubsub).aclose()
            with suppress(Exception):
                await cast(Any, client).aclose()
