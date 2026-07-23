"""SQLAlchemy repository for evaluation jobs and report metadata."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from data.clients.database import create_session_factory
from data.models.postgres import AssessmentReportModel, EvaluationJobModel
from schemas.evaluation import EvaluationJobResponse, EvaluationJobStatus


class EvaluationRepository:
    """Persist evaluation state using migration-managed SQLAlchemy tables."""

    def __init__(
        self,
        database_url: str,
        *,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self._session_factory = session_factory or create_session_factory(database_url)

    def save_job(
        self,
        job: EvaluationJobResponse,
        *,
        request_payload: dict[str, Any] | None = None,
    ) -> None:
        """Insert or update an evaluation job atomically."""

        with self._transaction() as session:
            model = session.get(EvaluationJobModel, job.job_id)
            if model is None:
                model = EvaluationJobModel(
                    job_id=job.job_id,
                    assessment_id=job.assessment_id,
                    candidate_assessment_id=job.candidate_assessment_id,
                    status=job.status.value,
                    attempt_count=job.attempt_count,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                )
                session.add(model)
            model.assessment_id = job.assessment_id
            model.candidate_assessment_id = job.candidate_assessment_id
            model.status = job.status.value
            model.attempt_count = job.attempt_count
            model.updated_at = job.updated_at
            model.error_message = job.error_message
            if request_payload is not None:
                model.request_json = request_payload
            model.result_json = (
                job.result.model_dump(mode="json") if job.result else None
            )

    def create_job_if_absent(
        self,
        job: EvaluationJobResponse,
        request_payload: dict[str, Any],
    ) -> tuple[EvaluationJobResponse, bool]:
        """Create one job per candidate assessment, safely under retries."""

        existing = self.get_job_by_candidate_assessment(job.candidate_assessment_id)
        if existing is not None:
            return existing, False
        try:
            self.save_job(job, request_payload=request_payload)
        except IntegrityError:
            existing = self.get_job_by_candidate_assessment(job.candidate_assessment_id)
            if existing is None:
                raise
            return existing, False
        return job, True

    def get_job(self, job_id: str) -> EvaluationJobResponse | None:
        """Return one job by ID."""

        with self._session() as session:
            model = session.get(EvaluationJobModel, job_id)
            return self._job_from_model(model) if model is not None else None

    def get_job_by_candidate_assessment(
        self,
        candidate_assessment_id: str,
    ) -> EvaluationJobResponse | None:
        """Return the idempotent job for a candidate assessment."""

        statement = select(EvaluationJobModel).where(
            EvaluationJobModel.candidate_assessment_id == candidate_assessment_id
        )
        with self._session() as session:
            model = session.scalar(statement)
            return self._job_from_model(model) if model is not None else None

    def get_request_payload(self, job_id: str) -> dict[str, Any] | None:
        """Return the validated JSON document used to create a job."""

        with self._session() as session:
            payload = session.scalar(
                select(EvaluationJobModel.request_json).where(
                    EvaluationJobModel.job_id == job_id
                )
            )
            return dict(payload) if payload is not None else None

    def list_jobs(
        self,
        assessment_id: str | None = None,
    ) -> list[EvaluationJobResponse]:
        """Return jobs, newest first."""

        statement = select(EvaluationJobModel)
        if assessment_id is not None:
            statement = statement.where(
                EvaluationJobModel.assessment_id == assessment_id
            )
        statement = statement.order_by(EvaluationJobModel.created_at.desc())
        with self._session() as session:
            models = session.scalars(statement).all()
            return [self._job_from_model(model) for model in models]

    def claim_pending_jobs(
        self,
        *,
        limit: int,
        lease_seconds: int,
    ) -> list[EvaluationJobResponse]:
        """Atomically claim pending or abandoned jobs for one worker."""

        now = datetime.now(UTC)
        stale_before = now - timedelta(seconds=lease_seconds)
        statement = (
            select(EvaluationJobModel)
            .where(
                or_(
                    EvaluationJobModel.status == EvaluationJobStatus.PENDING.value,
                    (EvaluationJobModel.status == EvaluationJobStatus.PROCESSING.value)
                    & (EvaluationJobModel.updated_at < stale_before),
                )
            )
            .order_by(EvaluationJobModel.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        with self._transaction() as session:
            models = list(session.scalars(statement).all())
            for model in models:
                if model.status == EvaluationJobStatus.PROCESSING.value:
                    model.attempt_count += 1
                model.status = EvaluationJobStatus.PROCESSING.value
                model.updated_at = now
            session.flush()
            return [self._job_from_model(model) for model in models]

    def claim_job(self, job_id: str) -> EvaluationJobResponse | None:
        """Atomically claim one pending job for inline or explicit processing."""

        statement = (
            select(EvaluationJobModel)
            .where(
                EvaluationJobModel.job_id == job_id,
                EvaluationJobModel.status == EvaluationJobStatus.PENDING.value,
            )
            .with_for_update(skip_locked=True)
        )
        with self._transaction() as session:
            model = session.scalar(statement)
            if model is None:
                return None
            model.status = EvaluationJobStatus.PROCESSING.value
            model.updated_at = datetime.now(UTC)
            session.flush()
            return self._job_from_model(model)

    def list_assessment_ids(self) -> list[str]:
        """Return assessment IDs with evaluation activity."""

        statement = (
            select(EvaluationJobModel.assessment_id)
            .distinct()
            .order_by(EvaluationJobModel.assessment_id)
        )
        with self._session() as session:
            return list(session.scalars(statement).all())

    def save_assessment_title(self, assessment_id: str, title: str) -> None:
        """Persist assessment title metadata."""

        with self._transaction() as session:
            report = session.get(AssessmentReportModel, assessment_id)
            if report is None:
                report = AssessmentReportModel(
                    assessment_id=assessment_id,
                    title=title,
                    report_status="pending",
                    generated_at=datetime.now(UTC),
                )
                session.add(report)
            else:
                report.title = title
                report.generated_at = datetime.now(UTC)

    def get_assessment_title(self, assessment_id: str) -> str:
        """Return stored title or a safe default."""

        with self._session() as session:
            title = session.scalar(
                select(AssessmentReportModel.title).where(
                    AssessmentReportModel.assessment_id == assessment_id
                )
            )
            return title or "Coding Assessment"

    def mark_report_ready(self, assessment_id: str) -> None:
        """Update report metadata after scoring completes."""

        with self._transaction() as session:
            report = session.get(AssessmentReportModel, assessment_id)
            if report is None:
                report = AssessmentReportModel(
                    assessment_id=assessment_id,
                    title="Coding Assessment",
                    report_status="ready",
                    generated_at=datetime.now(UTC),
                )
                session.add(report)
            else:
                report.report_status = "ready"
                report.generated_at = datetime.now(UTC)

    def has_jobs(self) -> bool:
        """Return whether any jobs exist."""

        with self._session() as session:
            return (
                session.scalar(select(EvaluationJobModel.job_id).limit(1)) is not None
            )

    def purge_terminal_jobs_before(self, cutoff: datetime) -> int:
        """Delete expired terminal jobs and orphaned report metadata."""

        with self._transaction() as session:
            result = session.execute(
                delete(EvaluationJobModel).where(
                    EvaluationJobModel.status.in_(
                        [
                            EvaluationJobStatus.COMPLETED.value,
                            EvaluationJobStatus.FAILED.value,
                        ]
                    ),
                    EvaluationJobModel.updated_at < cutoff,
                )
            )
            session.execute(
                delete(AssessmentReportModel).where(
                    ~exists().where(
                        EvaluationJobModel.assessment_id
                        == AssessmentReportModel.assessment_id
                    )
                )
            )
            return int(result.rowcount or 0) if isinstance(result, CursorResult) else 0

    @contextmanager
    def _session(self) -> Generator[Session]:
        session = self._session_factory()
        try:
            yield session
        finally:
            session.close()

    @contextmanager
    def _transaction(self) -> Generator[Session]:
        with self._session() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    @staticmethod
    def _job_from_model(model: EvaluationJobModel) -> EvaluationJobResponse:
        return EvaluationJobResponse.model_validate(
            {
                "job_id": model.job_id,
                "assessment_id": model.assessment_id,
                "candidate_assessment_id": model.candidate_assessment_id,
                "status": EvaluationJobStatus(model.status),
                "attempt_count": model.attempt_count,
                "created_at": model.created_at,
                "updated_at": model.updated_at,
                "error_message": model.error_message,
                "result": model.result_json,
            }
        )
