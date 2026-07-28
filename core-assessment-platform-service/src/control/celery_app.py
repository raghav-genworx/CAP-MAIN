"""Celery application.

COE names Celery as the background-job mechanism, and Compose has declared
``CELERY_BROKER_URL`` and ``CELERY_RESULT_BACKEND`` since long before the
consolidation -- but no code ever read them. This wires them up.

**PostgreSQL stays the source of truth, not Redis.** A job is a row in
``evaluation_jobs`` first; the Celery message only says "someone go look at this
row". That ordering is what makes a lost message survivable: the row is still
there, and the beat sweeper below picks it up. Losing the broker delays work, it
does not lose it.

The sweeper is the old polling worker, unchanged in behaviour -- it still claims
rows with ``SELECT ... FOR UPDATE SKIP LOCKED`` -- moved from a hand-rolled
``while True: sleep()`` onto beat. Retention purging moves the same way, off a
hand-computed 86,400-second timer.
"""

from celery import Celery

from config.settings import get_settings


def create_celery_app() -> Celery:
    """Build the Celery application from runtime settings."""

    settings = get_settings()

    app = Celery(
        "cap",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
        include=["control.tasks.evaluation"],
    )

    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        # Redeliver if a worker dies mid-task. Safe because the tasks are
        # idempotent against the job row rather than against the message.
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        # Evaluation runs Judge0-scored work and an LLM call; a short default
        # would kill legitimate jobs.
        task_soft_time_limit=600,
        task_time_limit=900,
        beat_schedule={
            "sweep-pending-evaluations": {
                "task": "cap.evaluation.sweep_pending",
                "schedule": settings.evaluation_worker_poll_interval_seconds,
            },
            "purge-expired-evaluations": {
                "task": "cap.evaluation.purge_expired",
                # Daily, matching the interval the old worker computed by hand.
                "schedule": 86_400.0,
            },
        },
    )
    return app


celery_app = create_celery_app()
