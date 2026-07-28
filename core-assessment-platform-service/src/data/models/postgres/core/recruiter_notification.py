"""Recruiter in-app notification inbox table."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from data.models.postgres.base import Base


class RecruiterNotificationModel(Base):
    """A dashboard notification card owned by a recruiter."""

    __tablename__ = "recruiter_notifications"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    recruiter_uid: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", server_default=""
    )
    body: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    assessment_id: Mapped[str | None] = mapped_column(String(36), index=True)
    slot_id: Mapped[str | None] = mapped_column(String(36), index=True)
    candidate_assessment_id: Mapped[str | None] = mapped_column(String(36))
    group_key: Mapped[str | None] = mapped_column(String(160), index=True)
    data: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false", index=True
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
