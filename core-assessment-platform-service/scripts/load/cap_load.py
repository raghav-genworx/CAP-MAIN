"""Guarded concurrent load harness for CAP candidate and worker workflows."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import stat
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from time import perf_counter
from typing import Any, TypedDict
from uuid import uuid4

import httpx
from pydantic import BaseModel, Field, SecretStr, ValidationError

CANDIDATE_SCENARIOS = ("checkpoint", "sample", "submit")
SUCCESS_STATUS_MIN = 200
SUCCESS_STATUS_MAX = 299


class QuestionFixture(BaseModel):
    """One candidate question used by the load workflow."""

    question_id: str = Field(min_length=1)
    source_code: str = Field(min_length=1, max_length=200_000)
    language: str = Field(min_length=1, max_length=40)
    current_question_order: int = Field(ge=1)


class CandidateFixture(BaseModel):
    """Sensitive candidate session fixture loaded only from a local file."""

    session_token: SecretStr = Field(min_length=12)
    questions: list[QuestionFixture] = Field(min_length=1)


class CandidateFixtureSet(BaseModel):
    """Validated candidate virtual-user fixture collection."""

    candidates: list[CandidateFixture] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class Observation:
    """One sanitized request measurement."""

    scenario: str
    elapsed_ms: float
    succeeded: bool
    status_code: int | None
    error_type: str = ""
    processed_count: int = 0


class LatencySummary(TypedDict):
    """Latency percentile measurements for one scenario."""

    p50: float
    p95: float
    p99: float
    max: float


class ScenarioSummary(TypedDict):
    """Aggregate measurements for one load scenario."""

    requests: int
    successes: int
    errors: int
    error_rate: float
    latency_ms: LatencySummary
    status_counts: dict[str, int]
    error_types: dict[str, int]
    processed_count: int


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 2)


def summarize(observations: Sequence[Observation]) -> dict[str, ScenarioSummary]:
    """Aggregate sanitized latency and error measurements by scenario."""

    grouped: dict[str, list[Observation]] = defaultdict(list)
    for observation in observations:
        grouped[observation.scenario].append(observation)

    summary: dict[str, ScenarioSummary] = {}
    for scenario, items in sorted(grouped.items()):
        latencies = [item.elapsed_ms for item in items]
        errors = sum(not item.succeeded for item in items)
        statuses = Counter(
            str(item.status_code) if item.status_code is not None else "transport_error"
            for item in items
        )
        error_types = Counter(item.error_type for item in items if item.error_type)
        summary[scenario] = {
            "requests": len(items),
            "successes": len(items) - errors,
            "errors": errors,
            "error_rate": round(errors / len(items), 4),
            "latency_ms": {
                "p50": _percentile(latencies, 0.50),
                "p95": _percentile(latencies, 0.95),
                "p99": _percentile(latencies, 0.99),
                "max": round(max(latencies, default=0.0), 2),
            },
            "status_counts": dict(sorted(statuses.items())),
            "error_types": dict(sorted(error_types.items())),
            "processed_count": sum(item.processed_count for item in items),
        }
    return summary


def _secure_fixture_path(path: Path) -> None:
    """Reject candidate token files readable by other local users."""

    if os.name == "nt":
        return
    permissions = stat.S_IMODE(path.stat().st_mode)
    if permissions & (stat.S_IRWXG | stat.S_IRWXO):
        raise ValueError(
            f"Fixture file {path} must not be accessible by group or other users; "
            "run chmod 600 on it."
        )


def load_candidate_fixtures(path: Path) -> CandidateFixtureSet:
    """Load and validate a permission-protected candidate fixture file."""

    _secure_fixture_path(path)
    try:
        return CandidateFixtureSet.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise ValueError(
            f"Unable to load valid candidate fixtures from {path}."
        ) from exc


def parse_scenarios(value: str) -> tuple[str, ...]:
    """Parse a unique ordered candidate scenario list."""

    scenarios = tuple(dict.fromkeys(item.strip().lower() for item in value.split(",")))
    invalid = [item for item in scenarios if item not in CANDIDATE_SCENARIOS]
    if not scenarios or invalid:
        allowed = ", ".join(CANDIDATE_SCENARIOS)
        raise ValueError(f"Scenarios must be selected from: {allowed}.")
    return scenarios


async def _request(
    client: httpx.AsyncClient,
    *,
    scenario: str,
    method: str,
    path: str,
    headers: dict[str, str],
    json_payload: dict[str, object] | None = None,
    params: dict[str, str | int | float | bool | None] | None = None,
    parse_processed_count: bool = False,
) -> Observation:
    started = perf_counter()
    try:
        response = await client.request(
            method,
            path,
            headers=headers,
            json=json_payload,
            params=params,
        )
        elapsed_ms = (perf_counter() - started) * 1000
        succeeded = SUCCESS_STATUS_MIN <= response.status_code <= SUCCESS_STATUS_MAX
        processed_count = 0
        error_type = "" if succeeded else "http_status"
        if succeeded and parse_processed_count:
            try:
                body = response.json()
                value = body.get("processed_count") if isinstance(body, dict) else None
                if not isinstance(value, int) or value < 0:
                    raise ValueError("invalid processed_count")
                processed_count = value
            except ValueError:
                succeeded = False
                error_type = "invalid_response"
        return Observation(
            scenario=scenario,
            elapsed_ms=elapsed_ms,
            succeeded=succeeded,
            status_code=response.status_code,
            error_type=error_type,
            processed_count=processed_count,
        )
    except httpx.HTTPError as exc:
        return Observation(
            scenario=scenario,
            elapsed_ms=(perf_counter() - started) * 1000,
            succeeded=False,
            status_code=None,
            error_type=type(exc).__name__,
        )


def _candidate_payload(
    scenario: str,
    fixture: CandidateFixture,
    question: QuestionFixture | None = None,
) -> tuple[str, dict[str, object]]:
    if scenario == "checkpoint":
        if question is None:
            raise ValueError("Checkpoint scenario requires a question fixture.")
        return (
            "/candidate/checkpoint",
            {
                "question_id": question.question_id,
                "source_code": question.source_code,
                "language": question.language,
                "current_question_order": question.current_question_order,
            },
        )
    if scenario == "sample":
        if question is None:
            raise ValueError("Sample scenario requires a question fixture.")
        return (
            "/candidate/run-sample",
            {
                "question_id": question.question_id,
                "source_code": question.source_code,
                "language": question.language,
            },
        )
    return (
        "/candidate/submit",
        {
            "answers": [
                {
                    "question_id": item.question_id,
                    "source_code": item.source_code,
                    "language": item.language,
                }
                for item in fixture.questions
            ],
            "auto_submit": False,
            "submission_tag": "load-test",
            "submission_message": "",
        },
    )


async def run_candidate(args: argparse.Namespace) -> list[Observation]:
    """Run concurrent candidate virtual-user workflows."""

    fixtures = load_candidate_fixtures(args.fixtures)
    scenarios = parse_scenarios(args.scenarios)
    if "submit" in scenarios and not args.allow_submit:
        raise ValueError("The submit scenario requires --allow-submit.")
    if "submit" in scenarios and args.iterations != 1:
        raise ValueError("The submit scenario requires exactly one iteration.")

    concurrency = min(args.concurrency, len(fixtures.candidates) * args.iterations)
    semaphore = asyncio.Semaphore(concurrency)
    observations: list[Observation] = []
    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )

    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        timeout=args.timeout_seconds,
        limits=limits,
    ) as client:

        async def virtual_user(fixture: CandidateFixture) -> None:
            async with semaphore:
                session_token = fixture.session_token.get_secret_value()
                headers = {
                    "Authorization": f"Bearer {session_token}",
                    "X-Request-ID": f"load-{uuid4().hex}",
                }
                for scenario in scenarios:
                    questions: Sequence[QuestionFixture | None] = (
                        (None,)
                        if scenario == "submit"
                        else fixture.questions[: args.questions_per_user]
                    )
                    for question in questions:
                        path, payload = _candidate_payload(
                            scenario,
                            fixture,
                            question,
                        )
                        observations.append(
                            await _request(
                                client,
                                scenario=scenario,
                                method="POST",
                                path=path,
                                headers=headers,
                                json_payload=payload,
                            )
                        )

        await asyncio.gather(
            *(
                virtual_user(fixture)
                for _ in range(args.iterations)
                for fixture in fixtures.candidates
            )
        )
    return observations


async def run_worker(args: argparse.Namespace) -> list[Observation]:
    """Run concurrent evaluation-worker batch claims."""

    if not args.allow_process:
        raise ValueError("Worker throughput requires --allow-process.")
    internal_token = os.getenv("CAP_LOAD_INTERNAL_SERVICE_TOKEN", "").strip()
    if not internal_token:
        raise ValueError("CAP_LOAD_INTERNAL_SERVICE_TOKEN is required.")

    semaphore = asyncio.Semaphore(args.concurrency)
    limits = httpx.Limits(
        max_connections=args.concurrency,
        max_keepalive_connections=args.concurrency,
    )
    observations: list[Observation] = []
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/"),
        timeout=args.timeout_seconds,
        limits=limits,
    ) as client:

        async def process_batch() -> None:
            async with semaphore:
                observations.append(
                    await _request(
                        client,
                        scenario="evaluation_worker",
                        method="POST",
                        path="/evaluations/worker/process-pending",
                        headers={
                            "X-Internal-Service-Token": internal_token,
                            "X-Request-ID": f"load-{uuid4().hex}",
                        },
                        params={"limit": args.batch_size},
                        parse_processed_count=True,
                    )
                )

        await asyncio.gather(*(process_batch() for _ in range(args.iterations)))
    return observations


def threshold_violations(
    summary: dict[str, ScenarioSummary],
    *,
    max_error_rate: float,
    max_p95_ms: float,
    min_processed: int,
) -> list[str]:
    """Return human-readable threshold failures without sensitive values."""

    violations: list[str] = []
    total_processed = 0
    for scenario, metrics in summary.items():
        error_rate = float(metrics["error_rate"])
        p95_ms = metrics["latency_ms"]["p95"]
        total_processed += metrics["processed_count"]
        if error_rate > max_error_rate:
            violations.append(
                f"{scenario} error rate {error_rate:.4f} exceeds {max_error_rate:.4f}"
            )
        if p95_ms > max_p95_ms:
            violations.append(
                f"{scenario} p95 {p95_ms:.2f}ms exceeds {max_p95_ms:.2f}ms"
            )
    if total_processed < min_processed:
        violations.append(
            f"processed job count {total_processed} is below required {min_processed}"
        )
    return violations


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--max-error-rate", type=float, default=0.01)
    parser.add_argument("--max-p95-ms", type=float, default=2_000.0)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line contract for both load scenarios."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    candidate = subparsers.add_parser("candidate")
    _add_common_arguments(candidate)
    candidate.add_argument(
        "--base-url",
        default="http://127.0.0.1:8002/api/v1",
    )
    candidate.add_argument("--fixtures", type=Path, required=True)
    candidate.add_argument("--scenarios", default="checkpoint,sample")
    candidate.add_argument("--questions-per-user", type=int, default=1)
    candidate.add_argument("--allow-submit", action="store_true")

    worker = subparsers.add_parser("worker")
    _add_common_arguments(worker)
    worker.add_argument(
        "--base-url",
        default="http://127.0.0.1:8004/api/v1",
    )
    worker.add_argument("--batch-size", type=int, default=20)
    worker.add_argument("--min-processed", type=int, default=1)
    worker.add_argument("--allow-process", action="store_true")
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    positive_values = {
        "concurrency": args.concurrency,
        "iterations": args.iterations,
        "timeout_seconds": args.timeout_seconds,
        "max_p95_ms": args.max_p95_ms,
    }
    invalid = [name for name, value in positive_values.items() if value <= 0]
    if invalid:
        raise ValueError(f"Values must be positive: {', '.join(invalid)}.")
    if not 0 <= args.max_error_rate <= 1:
        raise ValueError("max-error-rate must be between 0 and 1.")
    if args.command == "candidate" and args.questions_per_user <= 0:
        raise ValueError("questions-per-user must be positive.")
    if args.command == "worker":
        if not 1 <= args.batch_size <= 100:
            raise ValueError("batch-size must be between 1 and 100.")
        if args.min_processed < 0:
            raise ValueError("min-processed cannot be negative.")


async def _run(args: argparse.Namespace) -> int:
    _validate_args(args)
    observations = (
        await run_candidate(args)
        if args.command == "candidate"
        else await run_worker(args)
    )
    summary = summarize(observations)
    min_processed = args.min_processed if args.command == "worker" else 0
    violations = threshold_violations(
        summary,
        max_error_rate=args.max_error_rate,
        max_p95_ms=args.max_p95_ms,
        min_processed=min_processed,
    )
    output: dict[str, Any] = {
        "command": args.command,
        "concurrency": args.concurrency,
        "iterations": args.iterations,
        "summary": summary,
        "threshold_violations": violations,
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 2 if violations else 0


def main() -> int:
    """Run the selected load scenario and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args()
    try:
        return asyncio.run(_run(args))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
