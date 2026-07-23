"""Question bank domain exceptions."""

from core.exceptions.base import COEApplicationError


class QuestionNotFoundError(COEApplicationError):
    """Raised when a recruiter question cannot be found."""

    def __init__(self, message: str = "Question not found") -> None:
        super().__init__(message=message, status_code=404)


class QuestionBankValidationError(COEApplicationError):
    """Raised when a question payload is invalid."""

    def __init__(self, message: str = "Invalid question payload") -> None:
        super().__init__(message=message, status_code=400)


class QuestionBankStoreUnavailableError(COEApplicationError):
    """Raised when the question store cannot be reached."""

    def __init__(self, message: str = "Question store is unavailable") -> None:
        super().__init__(message=message, status_code=503)


class QuestionGuardrailError(COEApplicationError):
    """Raised when a question generation or code validation violates guardrails."""

    def __init__(self, message: str = "Guardrail violation detected") -> None:
        super().__init__(message=message, status_code=400)
