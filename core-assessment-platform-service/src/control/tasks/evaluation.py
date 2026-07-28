"""Evaluation background tasks.

Thin wrappers only. Every one of these delegates to ``EvaluationService``; none
contains scoring logic. That keeps the business rules callable from a request, a
task, or a test without going through a broker, and it means adopting Celery
changed no behaviour -- only what triggers it.
"""

import logging

from celery import shared_task

from config.settings import get_settings
from core.services.evaluation.ports import build_evaluation_maintenance_port
from utils.context import request_context

logger = logging.getLogger(__name__)


def _maintenance() -> object:
    """Build the queue-upkeep port from current settings."""

    return build_evaluation_maintenance_port(get_settings())


@shared_task(name="cap.evaluation.process_job", bind=True, max_retries=3)
def process_job(self, job_id: str, request_id: str | None = None) -> str:  # type: ignore[no-untyped-def]
    """Score one queued evaluation job.

    ``request_id`` is carried from whoever enqueued the work so the task's logs
    correlate with the request that caused it.

    The job row is the input, not the message payload: if this is redelivered
    after a crash, it re-reads current state rather than replaying stale data.
    """

    with request_context(request_id):
        service = _maintenance()
        try:
            result = service.process_job(job_id)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.exception("evaluation_task_failed job_id=%s", job_id)
            # Transient upstream failures (Groq, the database) are worth another
            # attempt; the sweeper would eventually catch it regardless, this just
            # gets there sooner.
            raise self.retry(exc=exc, countdown=30) from exc
        logger.info(
            "evaluation_task_completed job_id=%s status=%s", job_id, result.status
        )
        return str(result.status)


@shared_task(name="cap.evaluation.sweep_pending")
def sweep_pending() -> dict[str, int]:
    """Claim and process any pending jobs the broker did not deliver.

    This is the old polling worker's body. It remains the correctness backstop
    for the whole queue: a dropped Celery message, a worker killed between ack and
    completion, or a job enqueued while every worker was down all end up here.
    ``process_pending_jobs`` claims rows with ``FOR UPDATE SKIP LOCKED``, so
    running it concurrently with the task above cannot double-process a job.
    """

    settings = get_settings()
    run = _maintenance().process_pending_jobs(  # type: ignore[attr-defined]
        limit=settings.evaluation_worker_batch_size,
        lease_seconds=settings.evaluation_job_lease_seconds,
    )
    if run.processed_count:
        logger.info(
            "evaluation_sweep processed=%s completed=%s failed=%s",
            run.processed_count,
            run.completed_count,
            run.failed_count,
        )
    return {
        "processed": run.processed_count,
        "completed": run.completed_count,
        "failed": run.failed_count,
    }


@shared_task(name="cap.evaluation.purge_expired")
def purge_expired() -> dict[str, int]:
    """Delete evaluation evidence and report files past the retention window."""

    settings = get_settings()
    jobs, reports = _maintenance().purge_expired_data(  # type: ignore[attr-defined]
        settings.evaluation_retention_days
    )
    if jobs or reports:
        logger.info("evaluation_purge jobs=%s reports=%s", jobs, reports)
    return {"jobs": jobs, "reports": reports}
