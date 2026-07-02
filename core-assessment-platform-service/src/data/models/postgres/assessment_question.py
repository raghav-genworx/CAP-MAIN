"""Assessment question mapping table."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from data.models.postgres.base import Base


class AssessmentQuestionModel(Base):
    """Question configuration within an assessment template."""

    __tablename__ = "assessment_questions"

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
    question_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    question_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    marks: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
