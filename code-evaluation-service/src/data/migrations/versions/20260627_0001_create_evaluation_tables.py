"""Create evaluation jobs and report metadata tables.

Revision ID: 20260627_0001
Revises:
Create Date: 2026-06-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from data.models.postgres.base import EVALUATION_SCHEMA

revision: str = "20260627_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if EVALUATION_SCHEMA != "public":
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{EVALUATION_SCHEMA}"')
    op.create_table(
        "evaluation_jobs",
        sa.Column("job_id", sa.String(length=80), nullable=False),
        sa.Column("assessment_id", sa.String(length=80), nullable=False),
        sa.Column("candidate_assessment_id", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("request_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("result_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.PrimaryKeyConstraint("job_id"),
        schema=EVALUATION_SCHEMA,
    )
    op.create_index(
        "ix_evaluation_jobs_assessment_id",
        "evaluation_jobs",
        ["assessment_id"],
        schema=EVALUATION_SCHEMA,
    )
    op.create_index(
        "ix_evaluation_jobs_candidate_assessment",
        "evaluation_jobs",
        ["candidate_assessment_id"],
        schema=EVALUATION_SCHEMA,
    )
    op.create_index(
        "ix_evaluation_jobs_status_created",
        "evaluation_jobs",
        ["status", "created_at"],
        schema=EVALUATION_SCHEMA,
    )
    op.create_table(
        "assessment_reports",
        sa.Column("assessment_id", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("report_status", sa.String(length=20), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("assessment_id"),
        schema=EVALUATION_SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("assessment_reports", schema=EVALUATION_SCHEMA)
    op.drop_index(
        "ix_evaluation_jobs_status_created",
        table_name="evaluation_jobs",
        schema=EVALUATION_SCHEMA,
    )
    op.drop_index(
        "ix_evaluation_jobs_candidate_assessment",
        table_name="evaluation_jobs",
        schema=EVALUATION_SCHEMA,
    )
    op.drop_index(
        "ix_evaluation_jobs_assessment_id",
        table_name="evaluation_jobs",
        schema=EVALUATION_SCHEMA,
    )
    op.drop_table("evaluation_jobs", schema=EVALUATION_SCHEMA)
