"""Execution adapter contract tests."""

import logging
from types import SimpleNamespace

import httpx
import pytest

from core.exceptions.assessment import ExecutionAdapterError
from core.services import execution_adapter_service
from core.services.execution_adapter_service import ExecutionAdapterService
from schemas.question_bank import TestCase as QuestionTestCase


class _FakeClient:
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.payload: dict[str, object] | None = None

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def post(self, _url: str, *, json: dict[str, object]) -> httpx.Response:
        self.payload = json
        return self.response


def test_execute_batch_sends_execution_service_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Core should send the exact wrapper and test-case fields expected by execution."""

    request = httpx.Request("POST", "http://execution/api/v1/executions/batch")
    response = httpx.Response(
        200,
        request=request,
        json={
            "run_type": "final_hidden",
            "passed_count": 1,
            "total_count": 1,
            "results": [
                {
                    "input": "1 2\n",
                    "expected_output": "3\n",
                    "actual_output": "3",
                    "status": "Accepted",
                    "passed": True,
                }
            ],
        },
    )
    fake_client = _FakeClient(response)

    def client_factory(**kwargs: object) -> _FakeClient:
        assert kwargs["headers"] == {
            "X-Internal-Service-Token": "test-internal-service-token"
        }
        return fake_client

    monkeypatch.setattr(
        execution_adapter_service.httpx,
        "Client",
        client_factory,
    )

    service = ExecutionAdapterService(
        SimpleNamespace(
            code_execution_api_base_url="http://execution/api/v1",
            code_execution_request_timeout_seconds=10.0,
            internal_service_token="test-internal-service-token",
        )
    )

    service.execute_batch(
        source_code="print(input())",
        language="Python",
        test_cases=[
            QuestionTestCase(
                input="1 2\n",
                expected_output="3\n",
                is_sample=True,
                explanation="ignored by execution service",
            )
        ],
        run_type="final_hidden",
        time_limit_seconds=2,
        memory_limit_kb=128000,
    )

    assert fake_client.payload == {
        "source_code": "print(input())",
        "language": "python",
        "run_type": "final_hidden",
        "test_cases": [{"input": "1 2\n", "expected_output": "3\n"}],
        "cpu_time_limit": 2,
        "memory_limit": 128000,
    }


def test_execute_batch_logs_response_details_on_service_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    request = httpx.Request("POST", "http://execution/api/v1/executions/batch")
    response = httpx.Response(422, request=request, text='{"detail":"bad payload"}')
    fake_client = _FakeClient(response)
    monkeypatch.setattr(
        execution_adapter_service.httpx,
        "Client",
        lambda **_kwargs: fake_client,
    )
    service = ExecutionAdapterService(
        SimpleNamespace(
            code_execution_api_base_url="http://execution/api/v1",
            code_execution_request_timeout_seconds=10.0,
            internal_service_token="test-internal-service-token",
        )
    )

    with (
        caplog.at_level(logging.ERROR),
        pytest.raises(
            ExecutionAdapterError,
            match="Execution service request failed",
        ),
    ):
        service.execute_batch(
            source_code="print(1)",
            language="python",
            test_cases=[QuestionTestCase(input="1", expected_output="1")],
            run_type="final_hidden",
        )

    assert "status_code=422" in caplog.text
    assert '{"detail":"bad payload"}' not in caplog.text
    assert "payload_shape=" in caplog.text
    assert "source_code_length" in caplog.text
