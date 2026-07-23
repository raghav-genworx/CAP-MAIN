"""Move timing to test slots and persist question difficulty templates."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260630_0002"
down_revision: str | None = "20260627_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assessment_templates",
        sa.Column(
            "difficulty_blueprint",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "assessment_slots",
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE assessment_templates AS template
        SET difficulty_blueprint = COALESCE((
            SELECT jsonb_agg(selected.difficulty ORDER BY selected.question_order)
            FROM (
                SELECT question.difficulty, mapping.question_order
                FROM assessment_questions AS mapping
                JOIN question_bank_questions AS question
                  ON question.id = mapping.question_id
                WHERE mapping.assessment_id = template.id
                ORDER BY mapping.question_order
                LIMIT CASE
                    WHEN template.question_count_per_candidate > 0
                    THEN template.question_count_per_candidate
                    ELSE NULL
                END
            ) AS selected
        ), '[]'::jsonb)
        """
    )
    op.execute(
        """
        UPDATE assessment_slots AS slot
        SET duration_minutes = template.duration_minutes
        FROM assessment_templates AS template
        WHERE template.id = slot.assessment_id
        """
    )
    op.alter_column(
        "assessment_slots",
        "duration_minutes",
        nullable=False,
        server_default="60",
    )
    op.drop_column("assessment_questions", "time_limit_minutes")
    op.drop_column("question_bank_questions", "candidate_solve_time_minutes")


def downgrade() -> None:
    op.add_column(
        "question_bank_questions",
        sa.Column(
            "candidate_solve_time_minutes",
            sa.Integer(),
            server_default="45",
            nullable=False,
        ),
    )
    op.add_column(
        "assessment_questions",
        sa.Column("time_limit_minutes", sa.Integer(), nullable=True),
    )
    op.drop_column("assessment_slots", "duration_minutes")
    op.drop_column("assessment_templates", "difficulty_blueprint")
