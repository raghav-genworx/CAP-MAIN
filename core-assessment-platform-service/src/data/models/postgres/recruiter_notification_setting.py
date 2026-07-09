"""Recruiter notification preference table."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from data.models.postgres.base import Base


class RecruiterNotificationSettingModel(Base):
    """How a recruiter wants to receive dashboard notifications."""

    __tablename__ = "recruiter_notification_settings"

    setting_id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    recruiter_uid: Mapped[str] = mapped_column(
        String(128), index=True, unique=True, nullable=False
    )
    submission_notification_mode: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="milestone",
        server_default="milestone",
    )
    evaluation_notification_mode: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="milestone",
        server_default="milestone",
    )
    milestone_percentages: Mapped[list[int]] = mapped_column(
        JSONB,
        nullable=False,
        default=lambda: [25, 50, 75, 100],
        server_default="[25, 50, 75, 100]",
    )
    enable_submission_notifications: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    enable_evaluation_notifications: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    enable_report_ready_notification: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
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
