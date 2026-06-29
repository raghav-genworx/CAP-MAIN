"""Assessment template table."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from data.models.postgres.base import Base


class AssessmentTemplateModel(Base):
    """Recruiter-owned reusable assessment template."""

    __tablename__ = "assessment_templates"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    recruiter_uid: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    duration_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default="60"
    )
    passing_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=40.0, server_default="40.0"
    )
    test_case_score_weight: Mapped[float] = mapped_column(
        Float, nullable=False, default=60.0
    )
    coding_score_weight: Mapped[float] = mapped_column(
        Float, nullable=False, default=20.0
    )
    ai_score_weight: Mapped[float] = mapped_column(Float, nullable=False, default=20.0)
    allow_resume: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    shuffle_questions: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    question_count_per_candidate: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    show_score_to_candidate: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    proctoring_mode: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="basic",
    )
    hidden_feedback_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="none",
    )
    max_hidden_checks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hidden_check_cooldown_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
    )
    supported_languages: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        default="available",
        server_default="available",
    )
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
