"""Tests for evaluation scoring and API routes."""

import unittest
from datetime import UTC, datetime, timedelta
from os import utime
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.rest.app import create_app
from api.rest.dependencies import (
    evaluation_service_dependency,
    require_internal_service,
    settings_dependency,
)
from config.settings import Settings
from core.services.evaluation_service import EvaluationService
from core.services.report_pdf_service import ReportPdfService
from data.database import create_test_schema
from data.repositories.evaluation_repository import EvaluationRepository
from schemas.evaluation import (
    AICodeQualitySignal,
    EvaluationJobCreateRequest,
    EvaluationJobStatus,
    ExecutionVerdict,
    HiddenExecutionResult,
)
from schemas.evaluation import (
    TestReportRequest as ScheduledTestReportRequest,
)


def _database_url(tmpdir: str) -> str:
    return f"sqlite+pysqlite:///{tmpdir}/evaluation.sqlite3"


def _repository(tmpdir: str) -> EvaluationRepository:
    database_url = _database_url(tmpdir)
    create_test_schema(database_url)
    return EvaluationRepository(database_url)


def _result(case: int, passed: bool) -> HiddenExecutionResult:
    return HiddenExecutionResult(
        question_id="q_1",
        question_title="Array Balancer",
        test_case_id=f"case_{case}",
        passed=passed,
        verdict=ExecutionVerdict.ACCEPTED if passed else ExecutionVerdict.WRONG_ANSWER,
        execution_time_ms=100 + case,
        memory_kb=32_000,
        points=1,
        mandatory=case == 1,
        input=f"{case}\n",
        expected_output=f"{case}\n",
        actual_output=f"{case if passed else case + 1}\n",
        message="" if passed else "Wrong answer",
    )


def _request(
    candidate_assessment_id: str,
    candidate_name: str,
    passed_cases: int,
    ai_score: float,
) -> EvaluationJobCreateRequest:
    return EvaluationJobCreateRequest(
        assessment_id="assessment_unit",
        candidate_assessment_id=candidate_assessment_id,
        candidate_id=candidate_assessment_id.replace("ca", "cand"),
        candidate_name=candidate_name,
        candidate_email=f"{candidate_name.lower().replace(' ', '.')}@example.com",
        submission_id=candidate_assessment_id.replace("ca", "sub"),
        language="Python 3",
        source_code=(
            "# Question ID: q_1\n"
            "# Question: Array Balancer\n"
            "def solve():\n"
            "    return 1\n"
        ),
        hidden_results=[_result(case, case <= passed_cases) for case in range(1, 5)],
        ai_quality=AICodeQualitySignal(
            score=ai_score,
            approach="Structured approach.",
            time_complexity="O(n)",
            space_complexity="O(1)",
            readability="Readable.",
            maintainability="Maintainable.",
            strengths=["Simple"],
            weaknesses=[],
            improvements=[],
        ),
        time_taken_seconds=900,
    )


class EvaluationServiceTest(unittest.TestCase):
    def test_health_returns_503_when_database_is_unavailable(self) -> None:
        app = create_app()
        app.dependency_overrides[settings_dependency] = lambda: Settings(
            database_url="unsupported-database://unavailable"
        )
        client = TestClient(app)

        response = client.get("/api/v1/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "degraded")

    def test_production_rejects_local_internal_service_token(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                app_env="production",
                internal_service_token="change-me-local-internal-service-token",
            )

    def test_production_rejects_insecure_browser_origins(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(
                app_env="production",
                internal_service_token="production-internal-service-token",
                cors_allowed_origins="http://cap.example.com",
            )

    def test_demo_evaluation_seeding_requires_explicit_local_opt_in(self) -> None:
        self.assertFalse(Settings().seed_demo_evaluations)
        with self.assertRaises(ValidationError):
            Settings(
                app_env="production",
                internal_service_token="production-internal-service-token",
                cors_allowed_origins="https://cap.example.com",
                seed_demo_evaluations=True,
            )

    def test_default_service_constructor_does_not_seed_evaluations(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = EvaluationService(
                _repository(tmpdir),
                ReportPdfService(f"{tmpdir}/reports"),
            )

            self.assertEqual(service.list_assessment_ids(), [])

    def test_api_rejects_requests_without_internal_service_token(self) -> None:
        client = TestClient(create_app())

        response = client.get(
            "/api/v1/evaluations/assessment/assessment_algorithms_june"
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Unauthorized service request")
        self.assertIn("trace_id", response.json())

    def test_create_job_scores_and_ranks_candidates(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = EvaluationService(
                _repository(tmpdir),
                ReportPdfService(f"{tmpdir}/reports"),
                seed_demo_data=False,
            )

            service.create_job(_request("ca_unit_1", "First Candidate", 4, 80))
            service.create_job(_request("ca_unit_2", "Second Candidate", 2, 95))

            dashboard = service.get_assessment_dashboard("assessment_unit")

            self.assertEqual(dashboard.overview.completed_candidates, 2)
            self.assertEqual(dashboard.leaderboard[0].candidate_name, "First Candidate")
            self.assertEqual(dashboard.leaderboard[0].rank, 1)
            self.assertEqual(
                dashboard.leaderboard[0].scores.test_case_score,
                100,
            )
            question = dashboard.leaderboard[0].question_breakdown[0]
            self.assertEqual(question.submitted_code, "def solve():\n    return 1")
            self.assertEqual(len(question.test_cases), 4)
            self.assertEqual(question.test_cases[0].input, "1\n")
            self.assertEqual(dashboard.leaderboard[1].rank, 2)

    def test_test_report_is_scoped_and_generates_pdf(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = EvaluationService(
                _repository(tmpdir),
                ReportPdfService(f"{tmpdir}/reports"),
                seed_demo_data=False,
            )
            service.create_job(_request("ca_unit_1", "First Candidate", 4, 80))
            service.create_job(_request("ca_unit_2", "Second Candidate", 2, 95))
            request = ScheduledTestReportRequest(
                test_id="slot-1",
                test_title="Morning Batch",
                timezone_name="Asia/Kolkata",
                candidate_count=1,
                submitted_count=1,
                candidate_assessment_ids=["ca_unit_2"],
            )

            report = service.get_test_report("assessment_unit", request)
            generated = service.generate_test_report_pdf("assessment_unit", request)

            self.assertEqual(report.overview.total_candidates, 1)
            self.assertEqual(len(report.leaderboard), 1)
            self.assertEqual(report.leaderboard[0].candidate_name, "Second Candidate")
            self.assertEqual(report.leaderboard[0].rank, 1)
            self.assertEqual(generated.filename, "test-slot-1-report.pdf")
            self.assertTrue(generated.path.read_bytes().startswith(b"%PDF-1.4"))

    def test_create_job_is_idempotent_per_candidate_assessment(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = EvaluationService(
                _repository(tmpdir),
                ReportPdfService(f"{tmpdir}/reports"),
                seed_demo_data=False,
            )
            request = _request("ca_unit_1", "First Candidate", 4, 80)

            first = service.create_job(request)
            repeated = service.create_job(request)

            self.assertEqual(repeated.job_id, first.job_id)
            self.assertEqual(
                len(service.get_assessment_dashboard("assessment_unit").jobs),
                1,
            )

    def test_jobs_are_durable_across_service_instances(self) -> None:
        with TemporaryDirectory() as tmpdir:
            database_url = _database_url(tmpdir)
            create_test_schema(database_url)
            first_service = EvaluationService(
                EvaluationRepository(database_url),
                ReportPdfService(f"{tmpdir}/reports"),
                seed_demo_data=False,
            )
            first_service.create_job(_request("ca_unit_1", "First Candidate", 4, 80))

            second_service = EvaluationService(
                EvaluationRepository(database_url),
                ReportPdfService(f"{tmpdir}/reports"),
                seed_demo_data=False,
            )
            dashboard = second_service.get_assessment_dashboard("assessment_unit")

            self.assertEqual(dashboard.overview.completed_candidates, 1)
            self.assertEqual(dashboard.leaderboard[0].candidate_name, "First Candidate")

    def test_retention_purges_terminal_jobs_and_generated_reports(self) -> None:
        with TemporaryDirectory() as tmpdir:
            repository = _repository(tmpdir)
            report_dir = Path(tmpdir) / "reports"
            report_service = ReportPdfService(str(report_dir))
            service = EvaluationService(
                repository,
                report_service,
                seed_demo_data=False,
            )
            job = service.create_job(_request("ca_unit_1", "First Candidate", 4, 80))
            stale_at = datetime.now(UTC) - timedelta(days=400)
            repository.save_job(job.model_copy(update={"updated_at": stale_at}))
            stale_report = report_dir / "stale-scorecard.pdf"
            stale_report.write_bytes(b"%PDF-1.4")
            stale_timestamp = stale_at.timestamp()
            utime(stale_report, (stale_timestamp, stale_timestamp))

            deleted_jobs, deleted_reports = service.purge_expired_data(365)

            self.assertEqual(deleted_jobs, 1)
            self.assertEqual(deleted_reports, 1)
            self.assertIsNone(repository.get_job(job.job_id))
            self.assertFalse(stale_report.exists())

    def test_queued_jobs_can_be_processed_by_worker_flow(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = EvaluationService(
                _repository(tmpdir),
                ReportPdfService(f"{tmpdir}/reports"),
                seed_demo_data=False,
            )

            job = service.create_job(
                _request("ca_unit_1", "First Candidate", 4, 80),
                process_inline=False,
            )
            pending_dashboard = service.get_assessment_dashboard("assessment_unit")

            self.assertEqual(job.status, EvaluationJobStatus.PENDING)
            self.assertEqual(pending_dashboard.overview.pending_jobs, 1)
            self.assertEqual(pending_dashboard.overview.completed_candidates, 0)
            self.assertEqual(pending_dashboard.leaderboard, [])

            run = service.process_pending_jobs(limit=10)
            completed_job = service.get_job(job.job_id)

            self.assertEqual(run.processed_count, 1)
            self.assertEqual(run.completed_count, 1)
            self.assertEqual(run.failed_count, 0)
            self.assertEqual(completed_job.status, EvaluationJobStatus.COMPLETED)
            self.assertEqual(
                service.get_leaderboard("assessment_unit")[0].candidate_name,
                "First Candidate",
            )

    def test_worker_claim_reclaims_only_stale_processing_jobs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            repository = _repository(tmpdir)
            service = EvaluationService(
                repository,
                ReportPdfService(f"{tmpdir}/reports"),
                seed_demo_data=False,
            )
            queued = service.create_job(
                _request("ca_unit_1", "First Candidate", 4, 80),
                process_inline=False,
            )

            first_claim = repository.claim_pending_jobs(limit=1, lease_seconds=30)
            immediate_claim = repository.claim_pending_jobs(
                limit=1,
                lease_seconds=30,
            )
            repository.save_job(
                first_claim[0].model_copy(
                    update={"updated_at": datetime.now(UTC) - timedelta(seconds=31)}
                )
            )
            reclaimed = repository.claim_pending_jobs(limit=1, lease_seconds=30)

            self.assertEqual(first_claim[0].job_id, queued.job_id)
            self.assertEqual(first_claim[0].status, EvaluationJobStatus.PROCESSING)
            self.assertEqual(immediate_claim, [])
            self.assertEqual(reclaimed[0].job_id, queued.job_id)
            self.assertEqual(reclaimed[0].attempt_count, 2)

    def test_api_returns_seeded_dashboard(self) -> None:
        with TemporaryDirectory() as tmpdir:
            app = create_app()
            app.dependency_overrides[evaluation_service_dependency] = lambda: (
                EvaluationService(
                    _repository(tmpdir),
                    ReportPdfService(f"{tmpdir}/reports"),
                    seed_demo_data=True,
                )
            )
            app.dependency_overrides[require_internal_service] = lambda: None
            client = TestClient(app)

            response = client.get(
                "/api/v1/evaluations/assessment/assessment_algorithms_june"
            )

            self.assertEqual(response.status_code, 200)
            self.assertRegex(response.headers["x-request-id"], r"^[a-f0-9]{32}$")
            data = response.json()
            self.assertEqual(data["overview"]["completed_candidates"], 3)
            self.assertEqual(data["jobs"][0]["status"], EvaluationJobStatus.COMPLETED)
            self.assertGreaterEqual(len(data["leaderboard"]), 1)

            report_response = client.get(
                "/api/v1/evaluations/reports/assessment/assessment_algorithms_june"
            )
            self.assertEqual(report_response.status_code, 200)
            self.assertEqual(
                report_response.json()["overview"]["assessment_id"],
                "assessment_algorithms_june",
            )

            download_response = client.get(
                "/api/v1/evaluations/reports/assessment/"
                "assessment_algorithms_june/download"
            )
            self.assertEqual(download_response.status_code, 200)
            self.assertEqual(
                download_response.headers["content-type"],
                "application/pdf",
            )
            self.assertTrue(download_response.content.startswith(b"%PDF-1.4"))

            correlated_response = client.get(
                "/api/v1/evaluations/assessment/assessment_algorithms_june",
                headers={"X-Request-ID": "cap-test-request-42"},
            )
            self.assertEqual(
                correlated_response.headers["x-request-id"],
                "cap-test-request-42",
            )

            invalid_response = client.post(
                "/api/v1/evaluations/worker/process-pending?limit=0",
                headers={"X-Request-ID": "cap-validation-42"},
            )
            self.assertEqual(invalid_response.status_code, 422)
            self.assertEqual(
                invalid_response.json()["trace_id"],
                "cap-validation-42",
            )
            self.assertNotIn("input", str(invalid_response.json()["detail"]))

    def test_api_processes_pending_job_batch(self) -> None:
        with TemporaryDirectory() as tmpdir:
            service = EvaluationService(
                _repository(tmpdir),
                ReportPdfService(f"{tmpdir}/reports"),
                seed_demo_data=False,
            )
            app = create_app()
            app.dependency_overrides[evaluation_service_dependency] = lambda: service
            app.dependency_overrides[require_internal_service] = lambda: None
            client = TestClient(app)

            create_response = client.post(
                "/api/v1/evaluations/jobs?process_inline=false",
                json=_request(
                    "ca_unit_1",
                    "First Candidate",
                    4,
                    80,
                ).model_dump(mode="json"),
            )
            self.assertEqual(create_response.status_code, 201)
            self.assertEqual(
                create_response.json()["status"],
                EvaluationJobStatus.PENDING,
            )

            worker_response = client.post(
                "/api/v1/evaluations/worker/process-pending?limit=5"
            )

            self.assertEqual(worker_response.status_code, 200)
            self.assertEqual(worker_response.json()["processed_count"], 1)
            self.assertEqual(worker_response.json()["completed_count"], 1)
            self.assertEqual(
                worker_response.json()["jobs"][0]["status"],
                EvaluationJobStatus.COMPLETED,
            )


if __name__ == "__main__":
    unittest.main()
