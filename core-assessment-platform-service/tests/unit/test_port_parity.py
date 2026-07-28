"""Both transports must return the same thing.

``EXECUTION_TRANSPORT`` and ``EVALUATION_TRANSPORT`` are meant to be flippable in
either direction at any time, including as a rollback. That only holds if the
in-process path produces results indistinguishable from the HTTP path.

The risk is concrete: the in-process ports contain hand-written translation --
mapping Judge0 batch results into ``ExecutionCaseResult``, and re-validating the
evaluation service's schema family into core's. Nothing but a differential test
keeps those aligned with the HTTP adapter they shadow.
"""

import json

import httpx
import pytest
import respx

from config.settings import Settings
from core.services.evaluation.ports import (
    HttpEvaluationPort,
    InProcessEvaluationPort,
    _as_core_model,
    build_evaluation_port,
)
from core.services.execution.ports import (
    HttpExecutionPort,
    InProcessExecutionPort,
    build_execution_port,
)
from schemas.evaluation_reports import EvaluationJobResult
from schemas.execution import BatchExecutionResponse
from schemas.question_bank import TestCase as QuestionTestCase

pytestmark = pytest.mark.unit

EXEC_BASE = "http://execution.test/api/v1"
BATCH_URL = f"{EXEC_BASE}/executions/batch"

#: One passing case and one failing case, with every optional field populated so
#: a field dropped by either translation shows up as a difference.
UPSTREAM_BATCH = {
    "run_type": "sample_run",
    "passed_count": 1,
    "total_count": 2,
    "results": [
        {
            "input": "4",
            "expected_output": "16",
            "actual_output": "16",
            "status": "Accepted",
            "passed": True,
            "stderr": "",
            "compile_output": "",
            "message": "",
            "execution_time": "0.012",
            "memory_kb": 3200,
            "token": "tok-1",
        },
        {
            "input": "3",
            "expected_output": "999",
            "actual_output": "9",
            "status": "Wrong Answer",
            "passed": False,
            "stderr": "warn",
            "compile_output": "note",
            "message": "msg",
            "execution_time": "0.031",
            "memory_kb": 4100,
            "token": "tok-2",
        },
    ],
}

CASES = [
    QuestionTestCase(input="4", expected_output="16"),
    QuestionTestCase(input="3", expected_output="999"),
]


def _settings(**overrides: object) -> Settings:
    return Settings(
        code_execution_api_base_url=EXEC_BASE,
        internal_service_token="a-token-long-enough-to-pass-validation",
        **overrides,
    )


@respx.mock
def test_execution_transports_return_identical_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The hand-written in-process mapping matches the HTTP adapter's."""

    respx.post(BATCH_URL).mock(return_value=httpx.Response(200, json=UPSTREAM_BATCH))
    http_result = HttpExecutionPort(_settings()).execute_batch(
        source_code="print(1)",
        language="python",
        test_cases=CASES,
        run_type="sample_run",
    )

    # Feed the in-process port the same upstream payload, stubbed at the service
    # boundary so both paths normalise identical input.
    in_process = InProcessExecutionPort(_settings())

    async def fake_execute_batch(request: object) -> BatchExecutionResponse:
        return BatchExecutionResponse.model_validate(UPSTREAM_BATCH)

    monkeypatch.setattr(in_process._service, "execute_batch", fake_execute_batch)
    in_process_result = in_process.execute_batch(
        source_code="print(1)",
        language="python",
        test_cases=CASES,
        run_type="sample_run",
    )

    assert in_process_result == http_result


@pytest.mark.parametrize(
    ("source_code", "language", "cases", "reason"),
    [
        ("print(1)", "python", [], "no test cases"),
        (
            "print(1)",
            "python",
            [QuestionTestCase(input="1", expected_output="  ")],
            "no runnable expected outputs",
        ),
    ],
)
def test_execution_transports_short_circuit_identically(
    source_code: str, language: str, cases: list, reason: str
) -> None:
    """Both refuse the same inputs without contacting an upstream."""

    settings = _settings()
    kwargs = {
        "source_code": source_code,
        "language": language,
        "test_cases": cases,
        "run_type": "s",
    }

    with respx.mock:
        route = respx.post(BATCH_URL)
        http_result = HttpExecutionPort(settings).execute_batch(**kwargs)
        assert not route.called, reason

    assert InProcessExecutionPort(settings).execute_batch(**kwargs) == http_result


@pytest.mark.parametrize(
    ("bad_source", "bad_language"),
    [("   ", "python"), ("print(1)", "   ")],
)
def test_execution_transports_reject_bad_input_identically(
    bad_source: str, bad_language: str
) -> None:
    """Guard clauses match, so a caller's error handling is transport-agnostic."""

    from core.exceptions.assessment import ExecutionAdapterError

    settings = _settings()
    kwargs = {
        "source_code": bad_source,
        "language": bad_language,
        "test_cases": CASES,
        "run_type": "sample_run",
    }

    with pytest.raises(ExecutionAdapterError):
        HttpExecutionPort(settings).execute_batch(**kwargs)
    with pytest.raises(ExecutionAdapterError):
        InProcessExecutionPort(settings).execute_batch(**kwargs)


def test_schema_family_conversion_matches_the_wire_representation() -> None:
    """`_as_core_model` must equal what the HTTP path builds from real JSON.

    The in-process port converts between the two schema families with
    ``model_dump(mode="json")``. Dropping ``mode="json"`` would hand pydantic an
    ``EvaluationJobStatus`` enum where the core model declares ``str`` -- this
    pins that difference so the optimisation cannot be made silently.
    """

    from datetime import UTC, datetime

    from schemas.evaluation import EvaluationJobResponse, EvaluationJobStatus

    stamp = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)

    source = EvaluationJobResponse(
        job_id="job-1",
        assessment_id="assess-1",
        candidate_assessment_id="cand-1",
        status=EvaluationJobStatus.COMPLETED,
        attempt_count=2,
        created_at=stamp,
        updated_at=stamp,
    )

    over_the_wire = EvaluationJobResult.model_validate(
        json.loads(source.model_dump_json())
    )
    in_process = _as_core_model(source, EvaluationJobResult)

    assert in_process == over_the_wire
    assert isinstance(in_process.status, str)


def test_transport_setting_selects_the_port() -> None:
    """The flag is what decides, and the default stays on HTTP."""

    assert isinstance(build_execution_port(_settings()), HttpExecutionPort)
    assert isinstance(build_evaluation_port(_settings()), HttpEvaluationPort)

    in_proc = _settings(
        execution_transport="inprocess", evaluation_transport="inprocess"
    )
    assert isinstance(build_execution_port(in_proc), InProcessExecutionPort)
    assert isinstance(build_evaluation_port(in_proc), InProcessEvaluationPort)


def test_an_unknown_transport_is_rejected_at_startup() -> None:
    """A typo fails loudly at construction, not on the first candidate submit."""

    with pytest.raises(ValueError):
        _settings(execution_transport="in-process")
