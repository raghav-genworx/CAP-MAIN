"""Assessment and candidate-session domain exceptions."""

from core.exceptions.base import COEApplicationError


class AssessmentNotFoundError(COEApplicationError):
    """Raised when an assessment resource is missing."""

    def __init__(self, message: str = "Assessment not found") -> None:
        super().__init__(message=message, status_code=404)


class AssessmentValidationError(COEApplicationError):
    """Raised when an assessment payload is invalid."""

    def __init__(self, message: str = "Invalid assessment payload") -> None:
        super().__init__(message=message, status_code=400)


class AssessmentStoreUnavailableError(COEApplicationError):
    """Raised when the assessment store cannot be reached."""

    def __init__(self, message: str = "Assessment store is unavailable") -> None:
        super().__init__(message=message, status_code=503)


class CandidateInviteError(COEApplicationError):
    """Raised when an invite cannot be created, sent, or verified."""

    def __init__(self, message: str = "Candidate invite flow failed") -> None:
        super().__init__(message=message, status_code=400)


class CandidateSessionError(COEApplicationError):
    """Raised when a candidate session token is invalid or expired."""

    def __init__(self, message: str = "Candidate session is invalid") -> None:
        super().__init__(message=message, status_code=401)


class ExecutionAdapterError(COEApplicationError):
    """Raised when the execution adapter cannot complete a request."""

    def __init__(self, message: str = "Execution service request failed") -> None:
        super().__init__(message=message, status_code=502)


class EvaluationAdapterError(COEApplicationError):
    """Raised when the evaluation adapter cannot complete a request."""

    def __init__(self, message: str = "Evaluation service request failed") -> None:
        super().__init__(message=message, status_code=502)


class EmailDeliveryError(COEApplicationError):
    """Raised when a transactional email cannot be sent."""

    def __init__(self, message: str = "Email delivery failed") -> None:
        super().__init__(message=message, status_code=502)
