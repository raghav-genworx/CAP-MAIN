"""Idempotent candidate proctoring event table."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from data.models.postgres.base import Base


class CandidateProctorEventModel(Base):
    """One browser-observed violation accepted and counted by the server."""

    __tablename__ = "candidate_proctor_events"
    __table_args__ = (
        UniqueConstraint(
            "candidate_assessment_id",
            "client_event_id",
            name="uq_candidate_proctor_event_client_id",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    candidate_assessment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("candidate_assessments.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    client_event_id: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
