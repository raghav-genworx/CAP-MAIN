"""The sync-to-async bridge must work in every context that reaches it.

``run_async`` is the seam the whole async-edge conversion rests on: if it fails in
one execution context, the candidate submit path or the evaluation worker breaks
in a way unit tests of individual clients would not catch. So it is exercised in
all three, including the one where it must refuse.
"""

import threading

import anyio
import pytest
from starlette.concurrency import run_in_threadpool

from utils.helpers.concurrency import run_async

pytestmark = pytest.mark.unit


async def _echo(value: str) -> str:
    """Stand in for an async outbound adapter call."""

    return f"got:{value}"


async def _boom() -> str:
    raise ValueError("adapter failed")


def test_runs_from_a_fastapi_worker_thread() -> None:
    """The path every route takes: sync service inside run_in_threadpool."""

    def sync_service() -> str:
        return run_async(_echo, "from-worker")

    async def route() -> str:
        return await run_in_threadpool(sync_service)

    assert anyio.run(route) == "got:from-worker"


def test_runs_from_a_bare_thread_with_no_event_loop() -> None:
    """The path the evaluation worker takes: no host loop to submit to."""

    captured: list[str] = []

    def worker() -> None:
        captured.append(run_async(_echo, "from-bare-thread"))

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert captured == ["got:from-bare-thread"]


def test_runs_from_the_main_thread_with_no_event_loop() -> None:
    """The path `python -m worker` takes at start-up."""

    assert run_async(_echo, "from-main") == "got:from-main"


def test_refuses_to_run_inside_a_running_event_loop() -> None:
    """Bridging from the loop thread would deadlock, so it must fail loudly."""

    async def caller() -> None:
        run_async(_echo, "nope")

    with pytest.raises(RuntimeError, match="running event loop"):
        anyio.run(caller)


def test_propagates_the_coroutine_exception_from_a_worker_thread() -> None:
    """A failing adapter surfaces its own error, not a bridge error."""

    def sync_service() -> str:
        return run_async(_boom)

    async def route() -> str:
        return await run_in_threadpool(sync_service)

    with pytest.raises(ValueError, match="adapter failed"):
        anyio.run(route)


def test_propagates_the_coroutine_exception_with_no_host_loop() -> None:
    """Same guarantee on the worker path, which uses a different code branch."""

    with pytest.raises(ValueError, match="adapter failed"):
        run_async(_boom)


def test_forwards_positional_and_keyword_arguments() -> None:
    """Arguments reach the coroutine unchanged through both partial layers."""

    async def add(a: int, *, b: int) -> int:
        return a + b

    assert run_async(add, 1, b=2) == 3
