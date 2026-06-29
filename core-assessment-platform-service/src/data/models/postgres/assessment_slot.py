"""Assessment slot table."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from data.models.postgres.base import Base


class AssessmentSlotModel(Base):
    """Scheduled candidate batch for an assessment template."""

    __tablename__ = "assessment_slots"

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
    recruiter_uid: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    instructions_override: Mapped[str] = mapped_column(Text, nullable=False, default="")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone_name: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="Asia/Kolkata",
        server_default="Asia/Kolkata",
    )
    timezone_offset_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=330,
        server_default="330",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        default="scheduled",
    )
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_paused_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
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
