"""Server-sent event responses.

The platform streams three things to the browser: recruiter notifications, live
slot monitoring, and AI question-draft progress. Each is declared on its own
feature router so its path stays with the rest of that feature, but every one of
them builds its response here.

**Why this module exists.** The three endpoints had drifted apart -- monitoring
sent ``Cache-Control: no-cache, no-transform`` while the other two sent bare
``no-cache``. It never showed, because the gateway's ``_proxy_headers`` rewrote
the header on the way out and gave all three ``no-transform``. Folding the gateway
in removes that rewrite, so the drift would have become real: two streams losing
the directive that stops an intermediary buffering or re-encoding them, which for
an event stream means events arriving in batches or not at all.

Building every stream response from one place is what keeps that from recurring.
"""

from collections.abc import AsyncIterator, Iterator

from fastapi.responses import StreamingResponse

MEDIA_TYPE = "text/event-stream"

#: Headers every event stream must carry.
#:
#: ``no-transform`` is the load-bearing one: it tells proxies and CDNs not to
#: buffer or re-encode the body. ``X-Accel-Buffering: no`` is the nginx-specific
#: equivalent, and the deployed frontend does sit behind nginx.
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


#: Both are accepted because both are in use: notifications and slot monitoring
#: yield asynchronously, while the AI draft stream is a synchronous generator.
#: ``StreamingResponse`` handles either, running a sync generator in a threadpool.
StreamSource = (
    AsyncIterator[str] | AsyncIterator[bytes] | Iterator[str] | Iterator[bytes]
)


def event_stream(
    source: StreamSource,
    *,
    extra_headers: dict[str, str] | None = None,
) -> StreamingResponse:
    """Return a correctly-configured server-sent event response."""

    headers = dict(SSE_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    return StreamingResponse(source, media_type=MEDIA_TYPE, headers=headers)
