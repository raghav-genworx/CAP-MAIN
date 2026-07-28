"""Calling async code from the synchronous service layer.

COE requires async/await for I/O. The outbound adapters are async; the service
layer that drives them is still synchronous and runs inside
``run_in_threadpool``. This module is the single, temporary seam between the two.

It disappears when the database layer goes async and the services become
coroutines -- at which point every caller simply awaits.

Two execution contexts have to work:

* **A FastAPI worker thread.** Every route already hands off with
  ``run_in_threadpool``, which is anyio's ``to_thread.run_sync``. The coroutine is
  submitted back to the host event loop and this thread blocks for the result --
  the same blocking the synchronous ``httpx.Client`` did, except the I/O now runs
  on the loop.
* **A process with no event loop at all.** The evaluation worker (and the Celery
  worker replacing it) calls the same services from a plain thread, so there is no
  host loop to submit to and one has to be created for the call.
"""

from collections.abc import Awaitable, Callable
from functools import partial
from typing import ParamSpec, TypeVar

import anyio
from anyio import NoEventLoopError
from anyio.from_thread import run as run_in_host_loop

P = ParamSpec("P")
T = TypeVar("T")


def run_async(
    func: Callable[P, Awaitable[T]],
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Run an async callable from synchronous code and return its result.

    Raises:
        RuntimeError: if called from a thread that is itself running an event
            loop. Blocking that loop on its own coroutine would deadlock, so this
            fails loudly instead. Async callers must ``await`` directly.
    """

    _reject_async_context()

    call = partial(func, *args, **kwargs)
    try:
        # Succeeds only inside an anyio worker thread, where a token for the host
        # loop is on the thread local. anyio raises before awaiting anything, so a
        # NoEventLoopError here can never have come from the coroutine itself.
        #
        # (anyio 4.13 documents this as MissingTokenError, but no such class
        # exists -- `_token_or_error` raises NoEventLoopError. Verified, not
        # inferred from the docstring.)
        return run_in_host_loop(call)
    except NoEventLoopError:
        pass

    # No host loop: own one for the duration of the call.
    return anyio.run(call)


def _reject_async_context() -> None:
    """Fail fast when called from a thread that is running an event loop."""

    try:
        import asyncio

        asyncio.get_running_loop()
    except RuntimeError:
        return

    raise RuntimeError(
        "run_async() was called from a running event loop. Awaiting the callable "
        "directly is what you want here -- bridging would block the loop on its "
        "own coroutine and deadlock."
    )
