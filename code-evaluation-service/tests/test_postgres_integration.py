"""Opt-in PostgreSQL persistence integration test."""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from tempfile import TemporaryDirectory
from threading import Barrier
from uuid import uuid4

from core.services.evaluation_service import EvaluationService
from core.services.report_pdf_service import ReportPdfService
from data.repositories.evaluation_repository import EvaluationRepository
from schemas.evaluation import (
    EvaluationJobCreateRequest,
    EvaluationJobStatus,
    ExecutionVerdict,
    HiddenExecutionResult,
)

TEST_DATABASE_URL = os.getenv("EVALUATION_TEST_DATABASE_URL", "")


@unittest.skipUnless(
    TEST_DATABASE_URL.startswith("postgresql"),
    "EVALUATION_TEST_DATABASE_URL is required for PostgreSQL integration",
)
class PostgreSQLPersistenceIntegrationTest(unittest.TestCase):
    """Exercise JSONB persistence and retention against migrated PostgreSQL."""

    def test_job_round_trip_and_retention_cleanup(self) -> None:
        assessment_id = f"integration-{uuid4().hex}"
        candidate_assessment_id = f"candidate-{uuid4().hex}"
        repository = EvaluationRepository(TEST_DATABASE_URL)
        with TemporaryDirectory() as report_dir:
            service = EvaluationService(
                repository,
                ReportPdfService(report_dir),
                seed_demo_data=False,
            )
            completed = service.create_job(
                EvaluationJobCreateRequest(
                    assessment_id=assessment_id,
                    candidate_assessment_id=candidate_assessment_id,
                    candidate_id=f"candidate-{uuid4().hex}",
                    candidate_name="Integration Candidate",
                    candidate_email="integration@example.com",
                    submission_id=f"submission-{uuid4().hex}",
                    language="python",
                    source_code="print(1)",
                    hidden_results=[
                        HiddenExecutionResult(
                            question_id="question-1",
                            question_title="Integration Question",
                            test_case_id="case-1",
                            passed=True,
                            verdict=ExecutionVerdict.ACCEPTED,
                        )
                    ],
                )
            )

            restored = repository.get_job(completed.job_id)
            self.assertIsNotNone(restored)
            self.assertEqual(
                repository.get_request_payload(completed.job_id)["source_code"],
                "print(1)",
            )
            repository.save_job(
                completed.model_copy(
                    update={"updated_at": datetime.now(UTC) - timedelta(days=2)}
                )
            )

            deleted_jobs, _ = service.purge_expired_data(1)

            self.assertEqual(deleted_jobs, 1)
            self.assertIsNone(repository.get_job(completed.job_id))

    def test_concurrent_workers_claim_distinct_jobs(self) -> None:
        assessment_id = f"integration-{uuid4().hex}"
        repository = EvaluationRepository(TEST_DATABASE_URL)
        with TemporaryDirectory() as report_dir:
            service = EvaluationService(
                repository,
                ReportPdfService(report_dir),
                seed_demo_data=False,
            )
            queued = [
                service.create_job(
                    EvaluationJobCreateRequest(
                        assessment_id=assessment_id,
                        candidate_assessment_id=f"candidate-{uuid4().hex}",
                        candidate_id=f"candidate-{uuid4().hex}",
                        candidate_name=f"Concurrent Candidate {index}",
                        candidate_email=f"concurrent-{index}@example.com",
                        submission_id=f"submission-{uuid4().hex}",
                        language="python",
                        source_code="print(1)",
                        hidden_results=[
                            HiddenExecutionResult(
                                question_id="question-1",
                                question_title="Concurrent Question",
                                test_case_id="case-1",
                                passed=True,
                                verdict=ExecutionVerdict.ACCEPTED,
                            )
                        ],
                    ),
                    process_inline=False,
                )
                for index in range(2)
            ]
            barrier = Barrier(2)

            def claim_one() -> list[str]:
                barrier.wait()
                return [
                    job.job_id
                    for job in repository.claim_pending_jobs(
                        limit=1,
                        lease_seconds=300,
                    )
                ]

            with ThreadPoolExecutor(max_workers=2) as executor:
                claimed = list(executor.map(lambda _index: claim_one(), range(2)))

            claimed_ids = {job_id for batch in claimed for job_id in batch}
            self.assertEqual(claimed_ids, {job.job_id for job in queued})

            stale_at = datetime.now(UTC) - timedelta(days=2)
            for job in queued:
                processing = repository.get_job(job.job_id)
                self.assertIsNotNone(processing)
                repository.save_job(
                    processing.model_copy(
                        update={
                            "status": EvaluationJobStatus.COMPLETED,
                            "updated_at": stale_at,
                        }
                    )
                )
            repository.purge_terminal_jobs_before(datetime.now(UTC))
