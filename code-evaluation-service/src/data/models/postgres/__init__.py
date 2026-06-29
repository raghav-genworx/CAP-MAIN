"""Evaluation PostgreSQL model registry."""

from data.models.postgres.assessment_report import AssessmentReportModel
from data.models.postgres.base import Base
from data.models.postgres.evaluation_job import EvaluationJobModel

__all__ = ["AssessmentReportModel", "Base", "EvaluationJobModel"]
