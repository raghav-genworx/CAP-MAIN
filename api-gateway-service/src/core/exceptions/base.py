"""Application exception hierarchy."""


class COEApplicationError(Exception):
    """Base exception for expected application failures."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        """Initialize an application error."""

        super().__init__(message)
        self.message = message
        self.status_code = status_code
