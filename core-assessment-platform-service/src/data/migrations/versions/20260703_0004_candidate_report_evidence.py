"""store candidate report evidence

Revision ID: 20260703_0004
Revises: 20260701_0003
Create Date: 2026-07-03 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260703_0004"
down_revision: str | None = "20260701_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "candidate_assessments",
        sa.Column("tab_switch_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "candidate_assessments",
        sa.Column("copy_paste_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "candidate_assessments",
        sa.Column(
            "fullscreen_exit_count", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "candidate_assessments",
        sa.Column(
            "question_time_seconds",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("candidate_assessments", "question_time_seconds")
    op.drop_column("candidate_assessments", "fullscreen_exit_count")
    op.drop_column("candidate_assessments", "copy_paste_count")
    op.drop_column("candidate_assessments", "tab_switch_count")
