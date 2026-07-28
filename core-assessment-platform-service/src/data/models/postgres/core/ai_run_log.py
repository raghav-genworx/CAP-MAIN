"""AI gateway run log table."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from data.models.postgres.base import Base


class AIRunLogModel(Base):
    """Persisted trace of one AI gateway request."""

    __tablename__ = "ai_run_logs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    recruiter_uid: Mapped[str] = mapped_column(
        String(128), index=True, nullable=False, default=""
    )
    task_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    prompt_version: Mapped[str] = mapped_column(
        String(40), nullable=False, default="v1"
    )
    model_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    schema_name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    workflow_mode: Mapped[str] = mapped_column(
        String(40), nullable=False, default="interactive"
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    request_payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    response_payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
