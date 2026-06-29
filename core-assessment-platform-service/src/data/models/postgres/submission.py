"""Candidate submission table."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from data.models.postgres.base import Base


class SubmissionModel(Base):
    """Latest draft and final submitted code for one question."""

    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint(
            "candidate_assessment_id",
            "question_id",
            name="uq_submission_candidate_assessment_question",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    candidate_assessment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidate_assessments.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    assessment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assessment_templates.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    question_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    source_language: Mapped[str] = mapped_column(
        String(40), nullable=False, default="python"
    )
    draft_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    final_code: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        index=True,
        default="draft",
    )
    sample_run_result: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    hidden_check_result: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    final_hidden_result: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    last_saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
