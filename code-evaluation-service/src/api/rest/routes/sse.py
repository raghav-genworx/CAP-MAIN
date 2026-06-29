"""Server-sent event routes."""

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["streaming"])


async def _heartbeat_stream() -> AsyncIterator[str]:
    """Yield a small heartbeat event stream."""

    while True:
        yield "event: heartbeat\ndata: ok\n\n"
        await asyncio.sleep(10)


@router.get(
    "/events",
    summary="Stream service heartbeat events",
    description="Provides an async server-sent event heartbeat stream.",
)
async def events() -> StreamingResponse:
    """Return a server-sent event heartbeat stream."""

    return StreamingResponse(
        _heartbeat_stream(),
        media_type="text/event-stream",
    )
