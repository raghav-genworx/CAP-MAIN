"""Authentication and authorization exceptions."""

from core.exceptions.base import COEApplicationError


class AuthenticationError(COEApplicationError):
    """Raised when caller identity cannot be verified."""

    def __init__(self, message: str = "Authentication failed") -> None:
        """Initialize an authentication error."""

        super().__init__(message=message, status_code=401)


class AuthorizationError(COEApplicationError):
    """Raised when an authenticated user is not allowed to continue."""

    def __init__(self, message: str = "Not authorized") -> None:
        """Initialize an authorization error."""

        super().__init__(message=message, status_code=403)


class RoleStoreUnavailableError(COEApplicationError):
    """Raised when the Firebase role table cannot be reached."""

    def __init__(self, message: str = "Role store is unavailable") -> None:
        """Initialize a role store availability error."""

        super().__init__(message=message, status_code=503)
