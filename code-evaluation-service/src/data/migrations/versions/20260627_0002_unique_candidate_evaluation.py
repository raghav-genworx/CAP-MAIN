"""Guarantee one evaluation job per candidate assessment.

Revision ID: 20260627_0002
Revises: 20260627_0001
Create Date: 2026-06-27
"""

from collections.abc import Sequence

from alembic import op

from data.models.postgres.base import EVALUATION_SCHEMA

revision: str = "20260627_0002"
down_revision: str | None = "20260627_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_evaluation_jobs_candidate_assessment",
        "evaluation_jobs",
        ["candidate_assessment_id"],
        schema=EVALUATION_SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_evaluation_jobs_candidate_assessment",
        "evaluation_jobs",
        type_="unique",
        schema=EVALUATION_SCHEMA,
    )
