"""Execution-specific application errors."""

from core.exceptions.base import COEApplicationError


class UnsupportedLanguageError(COEApplicationError):
    """Raised when a requested language alias is not supported."""

    def __init__(self, language: str) -> None:
        """Initialize an unsupported language error."""

        super().__init__(f"Unsupported language: {language}", status_code=422)


class CodeExecutionTimeoutError(COEApplicationError):
    """Raised when Judge0 does not finish within the configured polling window."""

    def __init__(self) -> None:
        """Initialize an execution timeout error."""

        super().__init__("Code execution timed out.", status_code=504)


class Judge0ServiceError(COEApplicationError):
    """Raised when Judge0 cannot process a submission request."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        """Initialize a Judge0 service error."""

        super().__init__(message, status_code=status_code)
