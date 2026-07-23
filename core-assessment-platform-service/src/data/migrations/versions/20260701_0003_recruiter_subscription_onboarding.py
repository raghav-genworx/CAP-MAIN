"""add recruiter subscription onboarding

Revision ID: 20260701_0003
Revises: 20260630_0002
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260701_0003"
down_revision: str | None = "20260630_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_roles",
        sa.Column(
            "subscription_status",
            sa.String(length=40),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column(
        "user_roles",
        sa.Column("trial_started_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Recruiters that existed before onboarding was introduced keep their access.
    op.execute(
        sa.text(
            "UPDATE user_roles "
            "SET subscription_status = 'free_trial', trial_started_at = created_at"
        )
    )


def downgrade() -> None:
    op.drop_column("user_roles", "trial_started_at")
    op.drop_column("user_roles", "subscription_status")
