"""add answer validation mode fields

Revision ID: 20260708_0006
Revises: 20260706_0005
Create Date: 2026-07-08 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260708_0006"
down_revision: str | None = "20260706_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "question_bank_questions",
        sa.Column(
            "answer_validation_mode",
            sa.String(length=40),
            server_default="exact",
            nullable=False,
        ),
    )
    op.add_column(
        "question_bank_questions",
        sa.Column(
            "output_checker",
            sa.Text(),
            server_default="",
            nullable=False,
        ),
    )
    op.add_column(
        "question_bank_questions",
        sa.Column(
            "output_checker_explanation",
            sa.Text(),
            server_default="",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("question_bank_questions", "output_checker_explanation")
    op.drop_column("question_bank_questions", "output_checker")
    op.drop_column("question_bank_questions", "answer_validation_mode")
