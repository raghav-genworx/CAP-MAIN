"""create recruiter notification settings and inbox tables

Revision ID: 20260709_0007
Revises: 20260708_0006
Create Date: 2026-07-09 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260709_0007"
down_revision: str | None = "20260708_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recruiter_notification_settings",
        sa.Column("setting_id", sa.String(length=36), nullable=False),
        sa.Column("recruiter_uid", sa.String(length=128), nullable=False),
        sa.Column(
            "submission_notification_mode",
            sa.String(length=30),
            server_default="milestone",
            nullable=False,
        ),
        sa.Column(
            "evaluation_notification_mode",
            sa.String(length=30),
            server_default="milestone",
            nullable=False,
        ),
        sa.Column(
            "milestone_percentages",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[25, 50, 75, 100]",
            nullable=False,
        ),
        sa.Column(
            "enable_submission_notifications",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column(
            "enable_evaluation_notifications",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column(
            "enable_report_ready_notification",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("setting_id"),
    )
    op.create_index(
        "ix_recruiter_notification_settings_recruiter_uid",
        "recruiter_notification_settings",
        ["recruiter_uid"],
        unique=True,
    )

    op.create_table(
        "recruiter_notifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("recruiter_uid", sa.String(length=128), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=255), server_default="", nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=True),
        sa.Column("slot_id", sa.String(length=36), nullable=True),
        sa.Column("candidate_assessment_id", sa.String(length=36), nullable=True),
        sa.Column("group_key", sa.String(length=160), nullable=True),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "is_read",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_recruiter_notifications_recruiter_uid",
        "recruiter_notifications",
        ["recruiter_uid"],
    )
    op.create_index(
        "ix_recruiter_notifications_type",
        "recruiter_notifications",
        ["type"],
    )
    op.create_index(
        "ix_recruiter_notifications_assessment_id",
        "recruiter_notifications",
        ["assessment_id"],
    )
    op.create_index(
        "ix_recruiter_notifications_slot_id",
        "recruiter_notifications",
        ["slot_id"],
    )
    op.create_index(
        "ix_recruiter_notifications_group_key",
        "recruiter_notifications",
        ["group_key"],
    )
    op.create_index(
        "ix_recruiter_notifications_is_read",
        "recruiter_notifications",
        ["is_read"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recruiter_notifications_is_read",
        table_name="recruiter_notifications",
    )
    op.drop_index(
        "ix_recruiter_notifications_group_key",
        table_name="recruiter_notifications",
    )
    op.drop_index(
        "ix_recruiter_notifications_slot_id",
        table_name="recruiter_notifications",
    )
    op.drop_index(
        "ix_recruiter_notifications_assessment_id",
        table_name="recruiter_notifications",
    )
    op.drop_index(
        "ix_recruiter_notifications_type",
        table_name="recruiter_notifications",
    )
    op.drop_index(
        "ix_recruiter_notifications_recruiter_uid",
        table_name="recruiter_notifications",
    )
    op.drop_table("recruiter_notifications")

    op.drop_index(
        "ix_recruiter_notification_settings_recruiter_uid",
        table_name="recruiter_notification_settings",
    )
    op.drop_table("recruiter_notification_settings")
