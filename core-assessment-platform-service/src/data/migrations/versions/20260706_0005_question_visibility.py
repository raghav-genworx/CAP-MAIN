"""add question visibility

Revision ID: 20260706_0005
Revises: 20260703_0004
Create Date: 2026-07-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260706_0005"
down_revision: str | None = "20260703_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "question_bank_questions",
        sa.Column(
            "visibility",
            sa.String(length=20),
            server_default="private",
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_question_bank_questions_visibility"),
        "question_bank_questions",
        ["visibility"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_question_bank_questions_visibility"),
        table_name="question_bank_questions",
    )
    op.drop_column("question_bank_questions", "visibility")
