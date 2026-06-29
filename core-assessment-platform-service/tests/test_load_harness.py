"""Security and metrics contracts for the CAP load harness."""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import httpx
import pytest

HARNESS_PATH = Path(__file__).resolve().parents[1] / "scripts" / "load" / "cap_load.py"


def _load_harness() -> ModuleType:
    spec = importlib.util.spec_from_file_location("cap_load_harness", HARNESS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load CAP load harness")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_summary_calculates_latency_errors_and_processed_jobs() -> None:
    harness = _load_harness()
    observations = [
        harness.Observation("worker", 10.0, True, 200, processed_count=4),
        harness.Observation("worker", 20.0, True, 200, processed_count=3),
        harness.Observation("worker", 30.0, False, 503, error_type="http_status"),
    ]

    summary = harness.summarize(observations)["worker"]

    assert summary["requests"] == 3
    assert summary["error_rate"] == 0.3333
    assert summary["latency_ms"] == {
        "p50": 20.0,
        "p95": 30.0,
        "p99": 30.0,
        "max": 30.0,
    }
    assert summary["processed_count"] == 7
    assert summary["status_counts"] == {"200": 2, "503": 1}


def test_fixture_file_requires_private_permissions_and_masks_token(
    tmp_path: Path,
) -> None:
    harness = _load_harness()
    fixture_path = tmp_path / "candidate.local.json"
    fixture_path.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "session_token": "private-session-token",
                        "questions": [
                            {
                                "question_id": "question-1",
                                "source_code": "print(1)",
                                "language": "python",
                                "current_question_order": 1,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    fixture_path.chmod(0o644)

    with pytest.raises(ValueError, match="chmod 600"):
        harness.load_candidate_fixtures(fixture_path)

    fixture_path.chmod(0o600)
    fixtures = harness.load_candidate_fixtures(fixture_path)
    assert "private-session-token" not in str(fixtures)
    assert fixtures.candidates[0].session_token.get_secret_value() == (
        "private-session-token"
    )


def test_scenario_parser_rejects_unknown_operations() -> None:
    harness = _load_harness()

    assert harness.parse_scenarios("checkpoint,sample,checkpoint") == (
        "checkpoint",
        "sample",
    )
    with pytest.raises(ValueError, match="checkpoint, sample, submit"):
        harness.parse_scenarios("checkpoint,delete")


def test_worker_request_parses_processed_count_without_response_details() -> None:
    harness = _load_harness()
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={
                "processed_count": 5,
                "completed_count": 5,
                "failed_count": 0,
                "jobs": [{"sensitive": "not-retained"}],
            },
        )
    )

    async def make_request() -> object:
        async with httpx.AsyncClient(
            base_url="https://evaluation.test",
            transport=transport,
        ) as client:
            return await harness._request(
                client,
                scenario="evaluation_worker",
                method="POST",
                path="/evaluations/worker/process-pending",
                headers={"X-Internal-Service-Token": "secret"},
                parse_processed_count=True,
            )

    observation = asyncio.run(make_request())
    assert observation.processed_count == 5
    assert observation.succeeded is True
    assert "sensitive" not in str(observation)


def test_thresholds_fail_on_latency_error_rate_and_insufficient_work() -> None:
    harness = _load_harness()
    summary = harness.summarize(
        [
            harness.Observation("worker", 2_500.0, True, 200, processed_count=2),
            harness.Observation("worker", 100.0, False, 500),
        ]
    )

    violations = harness.threshold_violations(
        summary,
        max_error_rate=0.1,
        max_p95_ms=2_000,
        min_processed=10,
    )

    assert len(violations) == 3
    assert any("error rate" in item for item in violations)
    assert any("p95" in item for item in violations)
    assert any("processed job count" in item for item in violations)
