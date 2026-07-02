"""Evaluation adapter contract tests."""

from types import SimpleNamespace

import httpx
import pytest

from core.exceptions.assessment import (
    EvaluationAdapterError,
    EvaluationResourceNotFoundError,
)
from core.services import evaluation_adapter_service
from core.services.evaluation_adapter_service import EvaluationAdapterService


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

    def get(self, _url: str) -> httpx.Response:
        return self.response

    def request(
        self,
        _method: str,
        _url: str,
        **kwargs: object,
    ) -> httpx.Response:
        payload = kwargs.get("json")
        self.payload = payload if isinstance(payload, dict) else None
        return self.response


def test_create_job_sends_evaluation_service_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request("POST", "http://evaluation/api/v1/evaluations/jobs")
    response = httpx.Response(
        201,
        request=request,
        json={
            "job_id": "eval-1",
            "assessment_id": "assessment-1",
            "candidate_assessment_id": "candidate-assessment-1",
            "status": "completed",
            "attempt_count": 1,
            "created_at": "2026-06-26T10:00:00Z",
            "updated_at": "2026-06-26T10:00:00Z",
            "result": {
                "rank": 1,
                "scores": {
                    "test_case_score": 100,
                    "coding_score": 96,
                    "ai_score": 88,
                    "final_score": 96.8,
                    "percentage": 96.8,
                },
                "hidden_passed": 4,
                "hidden_total": 4,
                "total_execution_time_ms": 340,
                "peak_memory_kb": 32000,
                "ai_quality": {},
                "question_breakdown": [],
            },
        },
    )
    fake_client = _FakeClient(response)

    def client_factory(**kwargs: object) -> _FakeClient:
        assert kwargs["headers"] == {
            "X-Internal-Service-Token": "test-internal-service-token"
        }
        return fake_client

    monkeypatch.setattr(
        evaluation_adapter_service.httpx,
        "Client",
        client_factory,
    )
    payload = {
        "assessment_id": "assessment-1",
        "candidate_assessment_id": "candidate-assessment-1",
        "candidate_id": "candidate-1",
        "candidate_name": "Candidate One",
        "candidate_email": "candidate@example.com",
        "submission_id": "candidate-assessment-1",
        "language": "python",
        "source_code": "print(1)",
        "hidden_results": [
            {
                "question_id": "question-1",
                "question_title": "Question",
                "test_case_id": "question-1:1",
                "passed": True,
                "verdict": "accepted",
                "execution_time_ms": 100,
                "memory_kb": 32000,
                "points": 1,
                "mandatory": True,
            }
        ],
        "weights": {
            "test_case_weight": 60,
            "coding_weight": 20,
            "ai_weight": 20,
        },
    }
    service = EvaluationAdapterService(
        SimpleNamespace(
            code_evaluation_api_base_url="http://evaluation/api/v1",
            code_evaluation_request_timeout_seconds=10.0,
            internal_service_token="test-internal-service-token",
        )
    )

    job = service.create_job(payload)

    assert fake_client.payload == payload
    assert job.job_id == "eval-1"
    assert job.result is not None
    assert job.result.scores.final_score == 96.8


def test_create_job_raises_adapter_error_on_service_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request("POST", "http://evaluation/api/v1/evaluations/jobs")
    response = httpx.Response(503, request=request, text="unavailable")
    fake_client = _FakeClient(response)
    monkeypatch.setattr(
        evaluation_adapter_service.httpx,
        "Client",
        lambda **_kwargs: fake_client,
    )
    service = EvaluationAdapterService(
        SimpleNamespace(
            code_evaluation_api_base_url="http://evaluation/api/v1",
            code_evaluation_request_timeout_seconds=10.0,
            internal_service_token="test-internal-service-token",
        )
    )

    with pytest.raises(EvaluationAdapterError):
        service.create_job(
            {
                "assessment_id": "assessment-1",
                "candidate_assessment_id": "candidate-assessment-1",
                "source_code": "print(1)",
                "hidden_results": [],
            }
        )


def test_dashboard_404_is_reported_as_missing_evaluation_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request(
        "GET",
        "http://evaluation/api/v1/evaluations/assessment/assessment-1",
    )
    response = httpx.Response(404, request=request, text="missing")
    fake_client = _FakeClient(response)
    monkeypatch.setattr(
        evaluation_adapter_service.httpx,
        "Client",
        lambda **_kwargs: fake_client,
    )
    service = EvaluationAdapterService(
        SimpleNamespace(
            code_evaluation_api_base_url="http://evaluation/api/v1",
            code_evaluation_request_timeout_seconds=10.0,
            internal_service_token="test-internal-service-token",
        )
    )

    with pytest.raises(EvaluationResourceNotFoundError):
        service.get_dashboard("assessment-1")


def test_get_leaderboard_returns_scorecards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request(
        "GET",
        "http://evaluation/api/v1/evaluations/assessment/assessment-1/leaderboard",
    )
    response = httpx.Response(
        200,
        request=request,
        json=[
            {
                "candidate_assessment_id": "candidate-assessment-1",
                "rank": 1,
                "scores": {
                    "test_case_score": 100,
                    "coding_score": 96,
                    "ai_score": 88,
                    "final_score": 96.8,
                    "percentage": 96.8,
                },
            }
        ],
    )
    fake_client = _FakeClient(response)
    monkeypatch.setattr(
        evaluation_adapter_service.httpx,
        "Client",
        lambda **_kwargs: fake_client,
    )
    service = EvaluationAdapterService(
        SimpleNamespace(
            code_evaluation_api_base_url="http://evaluation/api/v1",
            code_evaluation_request_timeout_seconds=10.0,
            internal_service_token="test-internal-service-token",
        )
    )

    leaderboard = service.get_leaderboard("assessment-1")

    assert leaderboard[0].candidate_assessment_id == "candidate-assessment-1"
    assert leaderboard[0].rank == 1
    assert leaderboard[0].scores.final_score == 96.8


def test_download_test_report_posts_authorized_batch_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request(
        "POST",
        "http://evaluation/api/v1/evaluations/reports/assessment/assessment-1/"
        "tests/slot-1/download",
    )
    response = httpx.Response(
        200,
        request=request,
        content=b"%PDF-1.4 report",
        headers={
            "content-type": "application/pdf",
            "content-disposition": 'attachment; filename="morning-batch.pdf"',
        },
    )
    fake_client = _FakeClient(response)
    monkeypatch.setattr(
        evaluation_adapter_service.httpx,
        "Client",
        lambda **_kwargs: fake_client,
    )
    service = EvaluationAdapterService(
        SimpleNamespace(
            code_evaluation_api_base_url="http://evaluation/api/v1",
            code_evaluation_request_timeout_seconds=10.0,
            internal_service_token="test-internal-service-token",
        )
    )
    payload = {
        "test_id": "slot-1",
        "test_title": "Morning Batch",
        "candidate_count": 1,
        "submitted_count": 1,
        "candidate_assessment_ids": ["candidate-assessment-1"],
    }

    report = service.download_test_report("assessment-1", "slot-1", payload)

    assert fake_client.payload == payload
    assert report.content.startswith(b"%PDF-1.4")
    assert report.filename == "morning-batch.pdf"
