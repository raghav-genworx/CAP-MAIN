"""Durable evaluation job model."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from data.models.postgres.base import EvaluationBase

JSON_DOCUMENT = JSON().with_variant(JSONB, "postgresql")


class EvaluationJobModel(EvaluationBase):
    """Persist queued jobs, source evidence, and scorecard results."""

    __tablename__ = "evaluation_jobs"
    __table_args__ = (
        UniqueConstraint(
            "candidate_assessment_id",
            name="uq_evaluation_jobs_candidate_assessment",
        ),
        Index("ix_evaluation_jobs_assessment_id", "assessment_id"),
        Index("ix_evaluation_jobs_status_created", "status", "created_at"),
        Index(
            "ix_evaluation_jobs_candidate_assessment",
            "candidate_assessment_id",
        ),
    )

    job_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    assessment_id: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_assessment_id: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    request_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON_DOCUMENT)
