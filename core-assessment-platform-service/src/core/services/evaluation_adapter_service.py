"""Backward-compatible imports for the evaluation HTTP adapter."""

from typing import Any

from handlers.http_clients import evaluation as _implementation
from schemas.evaluation_reports import (
    CandidateEvaluationScorecard,
    EvaluationJobResult,
    EvaluationResult,
    EvaluationScores,
)

EvaluationAdapterService = _implementation.EvaluationAdapterService
EvaluationReportDownload = _implementation.EvaluationReportDownload
_compat: Any = _implementation
httpx = _compat.httpx

__all__ = [
    "CandidateEvaluationScorecard",
    "EvaluationAdapterService",
    "EvaluationJobResult",
    "EvaluationReportDownload",
    "EvaluationResult",
    "EvaluationScores",
    "httpx",
]
