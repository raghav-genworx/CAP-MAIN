"""API gateway exceptions."""

from core.exceptions.base import COEApplicationError


class UnknownUpstreamServiceError(COEApplicationError):
    """Raised when a requested upstream service is not registered."""

    def __init__(self, service_name: str) -> None:
        """Initialize an unknown upstream service error."""

        super().__init__(
            message=f"Unknown upstream service: {service_name}",
            status_code=404,
        )


class UpstreamServiceUnavailableError(COEApplicationError):
    """Raised when an upstream service cannot fulfill a gateway request."""

    def __init__(self, service_name: str) -> None:
        """Initialize an upstream service availability error."""

        super().__init__(
            message=f"Upstream service unavailable: {service_name}",
            status_code=503,
        )


class GatewayAuthenticationError(COEApplicationError):
    """Raised when gateway authentication fails."""

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message=message, status_code=401)


class GatewayAuthorizationError(COEApplicationError):
    """Raised when a verified identity cannot access a gateway route."""

    def __init__(self, message: str = "Not authorized") -> None:
        super().__init__(message=message, status_code=403)
