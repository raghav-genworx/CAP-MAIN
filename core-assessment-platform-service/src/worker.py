"""Background worker entry point.

Runs the Celery worker. Scheduling now lives in ``control.celery_app``'s beat
schedule, replacing this module's hand-rolled ``while True: sleep()`` loop and its
manually computed 86,400-second retention timer.

What did **not** change is how work is claimed. ``sweep_pending`` still calls
``process_pending_jobs``, which claims rows with ``SELECT ... FOR UPDATE SKIP
LOCKED``. That remains the correctness backstop for the queue, deliberately: Redis
carries a hint that a job exists, PostgreSQL carries the job.

``--once`` is retained -- it drains one batch and exits, which is what the old flag
did and what a one-shot Cloud Run job needs.

    python -m worker            # Celery worker, with embedded beat
    python -m worker --once     # drain one pending batch, then exit
"""

from __future__ import annotations

import argparse
import logging

from config.settings import get_settings
from control.celery_app import celery_app
from observability.logging.logger import configure_logging

logger = logging.getLogger(__name__)


def run_once() -> None:
    """Process one pending batch synchronously and return.

    Deliberately bypasses the broker: this is for draining and for smoke tests,
    where a round trip through Redis would only add a way to fail.
    """

    from control.tasks.evaluation import sweep_pending

    result = sweep_pending()
    logger.info(
        "worker_drained processed=%s completed=%s failed=%s",
        result["processed"],
        result["completed"],
        result["failed"],
    )


def run_worker(*, with_beat: bool = True) -> None:
    """Run the Celery worker, optionally embedding the beat scheduler.

    Embedded beat suits a single-worker deployment, which is what Compose and the
    Cloud Run worker pool both run. Scaling past one worker means moving beat to
    its own process -- two schedulers would each fire the sweep.
    """

    settings = get_settings()
    argv = ["worker", f"--loglevel={settings.log_level.lower()}", "--concurrency=1"]
    if with_beat:
        argv += ["--beat", f"--schedule={settings.celery_beat_schedule_path}"]
    celery_app.worker_main(argv)


def main() -> None:
    """Parse arguments and start the worker."""

    parser = argparse.ArgumentParser(description="Run CAP background work.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process one pending batch and exit, without using the broker.",
    )
    parser.add_argument(
        "--no-beat",
        action="store_true",
        help="Run the worker without an embedded scheduler.",
    )
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)

    if args.once:
        run_once()
        return
    run_worker(with_beat=not args.no_beat)


if __name__ == "__main__":
    main()
