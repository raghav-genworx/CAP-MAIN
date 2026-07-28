"""Ambient request context.

The request ID is set once by the logging middleware and read anywhere downstream
-- a service, a repository, a Celery task -- without threading it through every
signature. A ``ContextVar`` is the right carrier: it is isolated per task and per
thread, so a value set while handling one request cannot leak into another, which
matters because the service layer runs in ``run_in_threadpool`` worker threads.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("cap_request_id", default=None)


def get_request_id() -> str | None:
    """Return the correlation ID for the work in flight, if one is set."""

    return _request_id.get()


def set_request_id(request_id: str | None) -> None:
    """Set the correlation ID for the current context."""

    _request_id.set(request_id)


@contextmanager
def request_context(request_id: str | None) -> Iterator[None]:
    """Bind a correlation ID for the duration of the block, then restore it.

    Used by entry points that are not HTTP requests -- the evaluation worker, and
    the Celery tasks that replace it -- so their logs correlate with the request
    that enqueued the work.
    """

    token = _request_id.set(request_id)
    try:
        yield
    finally:
        _request_id.reset(token)
