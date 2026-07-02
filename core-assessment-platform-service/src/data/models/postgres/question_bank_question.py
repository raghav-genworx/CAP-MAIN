"""Question bank table."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from data.models.postgres.base import Base


class QuestionBankQuestionModel(Base):
    """Recruiter-owned coding question."""

    __tablename__ = "question_bank_questions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    recruiter_uid: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    problem_statement: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    topics: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    category: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    constraints: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_format: Mapped[str] = mapped_column(Text, nullable=False, default="")
    input_explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    output_format: Mapped[str] = mapped_column(Text, nullable=False, default="")
    output_explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sample_test_cases: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    hidden_test_cases: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    reference_solution: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reference_language: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="python",
    )
    supported_languages: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    execution_time_limit_seconds: Mapped[int] = mapped_column(
        nullable=False,
        default=2,
    )
    memory_limit_mb: Mapped[int] = mapped_column(nullable=False, default=256)
    metadata_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
    )
    difficulty_source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="legacy",
    )
    validation_report: Mapped[dict[str, object] | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    validation_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="not_run",
    )
    validation_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    reference_solutions: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    solution_approach: Mapped[str] = mapped_column(Text, nullable=False, default="")
    time_complexity: Mapped[str] = mapped_column(
        String(160), nullable=False, default=""
    )
    space_complexity: Mapped[str] = mapped_column(
        String(160), nullable=False, default=""
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        default="draft",
    )
    creation_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="manual",
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
