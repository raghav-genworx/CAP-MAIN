"""The execution adapter after the async conversion.

This adapter sits on the candidate hot path -- `run-sample`, `hidden-check` and
`submit` all go through it. The transport is now async while every caller is still
synchronous, so the thing worth proving is that the whole chain works end to end
through a real ``httpx`` client, not just that it type-checks.
"""

import httpx
import pytest
import respx
from starlette.concurrency import run_in_threadpool

from config.settings import Settings
from core.exceptions.assessment import ExecutionAdapterError
from handlers.http_clients.execution import ExecutionAdapterService

# Aliased: pytest would otherwise try to collect the schema as a test class.
from schemas.question_bank import TestCase as QuestionTestCase

pytestmark = pytest.mark.unit

BATCH_URL = "http://execution.test/api/v1/executions/batch"


@pytest.fixture
def adapter() -> ExecutionAdapterService:
    """Return an adapter pointed at a stubbed upstream."""

    settings = Settings(
        code_execution_api_base_url="http://execution.test/api/v1",
        internal_service_token="a-token-long-enough-to-pass-validation",
    )
    return ExecutionAdapterService(settings)


def _batch_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "passed_count": 1,
            "total_count": 2,
            "results": [
                {
                    "input": "1",
                    "expected_output": "1",
                    "actual_output": "1",
                    "status": "Accepted",
                    "passed": True,
                },
                {
                    "input": "2",
                    "expected_output": "4",
                    "actual_output": "5",
                    "status": "Wrong Answer",
                    "passed": False,
                },
            ],
        },
    )


CASES = [
    QuestionTestCase(input="1", expected_output="1"),
    QuestionTestCase(input="2", expected_output="4"),
]


def _run(adapter: ExecutionAdapterService) -> tuple[list, int, int]:
    return adapter.execute_batch(
        source_code="print(1)",
        language="python",
        test_cases=CASES,
        run_type="sample",
    )


@respx.mock
def test_sync_wrapper_works_from_a_plain_call(
    adapter: ExecutionAdapterService,
) -> None:
    """The worker path: no event loop anywhere, bridge creates one."""

    route = respx.post(BATCH_URL).mock(return_value=_batch_response())

    results, passed, total = _run(adapter)

    assert route.called
    assert (passed, total) == (1, 2)
    assert [r.passed for r in results] == [True, False]


@respx.mock
def test_sync_wrapper_works_from_a_fastapi_worker_thread(
    adapter: ExecutionAdapterService,
) -> None:
    """The request path: sync service inside run_in_threadpool, host loop present.

    This is the branch that actually runs in production and the one a naive
    implementation gets wrong.
    """

    import anyio

    respx.post(BATCH_URL).mock(return_value=_batch_response())

    async def route() -> tuple[list, int, int]:
        return await run_in_threadpool(_run, adapter)

    results, passed, total = anyio.run(route)

    assert (passed, total) == (1, 2)
    assert len(results) == 2


@respx.mock
def test_the_internal_service_token_is_sent(
    adapter: ExecutionAdapterService,
) -> None:
    """Judge0 access stays behind the trusted-service credential."""

    route = respx.post(BATCH_URL).mock(return_value=_batch_response())

    _run(adapter)

    sent = route.calls.last.request
    assert sent.headers["X-Internal-Service-Token"] == (
        "a-token-long-enough-to-pass-validation"
    )


@respx.mock
def test_transport_failure_becomes_a_domain_error(
    adapter: ExecutionAdapterService,
) -> None:
    """Callers see ExecutionAdapterError, never a raw httpx exception."""

    respx.post(BATCH_URL).mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(ExecutionAdapterError):
        _run(adapter)


@respx.mock
def test_upstream_error_status_becomes_a_domain_error(
    adapter: ExecutionAdapterService,
) -> None:
    """A 500 from the execution service is translated, not leaked."""

    respx.post(BATCH_URL).mock(return_value=httpx.Response(500, json={}))

    with pytest.raises(ExecutionAdapterError):
        _run(adapter)


def test_empty_test_cases_short_circuit_without_a_request(
    adapter: ExecutionAdapterService,
) -> None:
    """No upstream call when there is nothing to run."""

    with respx.mock:
        route = respx.post(BATCH_URL)
        results, passed, total = adapter.execute_batch(
            source_code="print(1)",
            language="python",
            test_cases=[],
            run_type="sample",
        )

    assert not route.called
    assert (results, passed, total) == ([], 0, 0)
