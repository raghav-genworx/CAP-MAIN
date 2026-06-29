"""Queued evaluation worker entry point."""

from __future__ import annotations

import argparse
import logging
import time

from config.settings import get_settings
from core.services.evaluation_service import get_evaluation_service
from observability.logging.config import configure_logging

logger = logging.getLogger(__name__)


def run_worker(*, once: bool = False) -> None:
    """Poll durable storage for queued evaluation jobs and process them."""

    settings = get_settings()
    configure_logging(settings.log_level)
    service = get_evaluation_service(
        settings.database_url,
        settings.evaluation_report_dir,
        settings.seed_demo_evaluations,
        settings.groq_api_key,
        settings.groq_base_url,
        settings.groq_model,
        settings.groq_request_timeout_seconds,
        settings.groq_retry_count,
        settings.groq_max_source_chars,
    )

    logger.info(
        "Starting evaluation worker with batch_size=%s poll_interval=%ss",
        settings.evaluation_worker_batch_size,
        settings.evaluation_worker_poll_interval_seconds,
    )
    next_retention_run = 0.0
    while True:
        monotonic_now = time.monotonic()
        if monotonic_now >= next_retention_run:
            deleted_jobs, deleted_reports = service.purge_expired_data(
                settings.evaluation_retention_days
            )
            if deleted_jobs or deleted_reports:
                logger.info(
                    "Purged expired evaluation data: jobs=%s reports=%s",
                    deleted_jobs,
                    deleted_reports,
                )
            next_retention_run = monotonic_now + 86_400
        run = service.process_pending_jobs(
            limit=settings.evaluation_worker_batch_size,
            lease_seconds=settings.evaluation_job_lease_seconds,
        )
        if run.processed_count:
            logger.info(
                "Processed %s evaluation jobs: %s completed, %s failed",
                run.processed_count,
                run.completed_count,
                run.failed_count,
            )
        if once:
            return
        time.sleep(settings.evaluation_worker_poll_interval_seconds)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run queued CAP evaluations.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process one pending batch and exit.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    run_worker(once=_parse_args().once)
