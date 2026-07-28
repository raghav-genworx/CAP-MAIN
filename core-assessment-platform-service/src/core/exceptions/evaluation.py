"""Evaluation-specific application errors."""

from core.exceptions.base import COEApplicationError


class EvaluationJobNotFoundError(COEApplicationError):
    """Raised when an evaluation job cannot be found."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Evaluation job '{job_id}' was not found.", 404)


class AssessmentNotFoundError(COEApplicationError):
    """Raised when an assessment has no evaluation workspace."""

    def __init__(self, assessment_id: str) -> None:
        super().__init__(f"Assessment '{assessment_id}' was not found.", 404)


class EvaluationRetryError(COEApplicationError):
    """Raised when a job cannot be retried."""

    def __init__(self, message: str) -> None:
        super().__init__(message, 409)
