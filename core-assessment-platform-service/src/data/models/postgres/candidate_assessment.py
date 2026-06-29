"""Candidate assessment assignment table."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from data.models.postgres.base import Base


class CandidateAssessmentModel(Base):
    """Candidate assignment to a slot and its runtime state."""

    __tablename__ = "candidate_assessments"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    assessment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assessment_templates.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    slot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("assessment_slots.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    candidate_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    recruiter_uid: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    invite_token_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, default=""
    )
    email_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        default="not_started",
    )
    hidden_checks_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_question_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    invite_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submission_tag: Mapped[str] = mapped_column(
        String(60), nullable=False, default="", server_default=""
    )
    submission_message: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    last_hidden_check_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_score: Mapped[float | None] = mapped_column(Float)
    percentage: Mapped[float | None] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer)
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
