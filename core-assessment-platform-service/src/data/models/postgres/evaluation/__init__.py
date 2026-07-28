"""Evaluation PostgreSQL model registry.

Kept separate from the core registry so each Alembic tree targets only its own
metadata.
"""

from data.models.postgres.base import EvaluationBase
from data.models.postgres.evaluation.assessment_report import AssessmentReportModel
from data.models.postgres.evaluation.evaluation_job import EvaluationJobModel

__all__ = ["AssessmentReportModel", "EvaluationBase", "EvaluationJobModel"]
