"""add versioned drafts and idempotent proctoring events

Revision ID: 20260720_0008
Revises: 20260709_0007
Create Date: 2026-07-20 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260720_0008"
down_revision: str | None = "20260709_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_table(
        "candidate_proctor_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("candidate_assessment_id", sa.String(length=36), nullable=False),
        sa.Column("client_event_id", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_assessment_id"],
            ["candidate_assessments.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "candidate_assessment_id",
            "client_event_id",
            name="uq_candidate_proctor_event_client_id",
        ),
    )
    op.create_index(
        "ix_candidate_proctor_events_candidate_assessment_id",
        "candidate_proctor_events",
        ["candidate_assessment_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_candidate_proctor_events_candidate_assessment_id",
        table_name="candidate_proctor_events",
    )
    op.drop_table("candidate_proctor_events")
    op.drop_column("submissions", "version")
