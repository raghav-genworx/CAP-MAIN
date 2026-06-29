"""Assessment report metadata model."""

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from data.models.postgres.base import Base


class AssessmentReportModel(Base):
    """Track report readiness without storing generated PDF bytes."""

    __tablename__ = "assessment_reports"

    assessment_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    report_status: Mapped[str] = mapped_column(String(20), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
