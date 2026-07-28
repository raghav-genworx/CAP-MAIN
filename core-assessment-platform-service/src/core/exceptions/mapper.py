"""Exception to HTTP status mapping.

Domain code raises domain errors and never names a transport status. Every
``COEApplicationError`` already carries ``status_code``, so this module is the one
place that decides how anything else becomes a response -- keeping the choice out
of the error handler's control flow and giving the boundary a single audit point.
"""

import logging

from core.exceptions.base import COEApplicationError

logger = logging.getLogger(__name__)

INTERNAL_SERVER_ERROR = 500
UNPROCESSABLE_ENTITY = 422

#: Never leak an unexpected exception's message: it can carry a connection string,
#: a token, or candidate source code.
INTERNAL_ERROR_DETAIL = "Internal server error"


def status_code_for(exc: BaseException) -> int:
    """Return the HTTP status an exception should produce."""

    if isinstance(exc, COEApplicationError):
        return exc.status_code
    return INTERNAL_SERVER_ERROR


def detail_for(exc: BaseException) -> str:
    """Return the client-safe ``detail`` for an exception.

    Domain errors are written to be read by a user and are passed through. Anything
    else is replaced by a fixed string, because the frontend surfaces ``detail``
    directly in the UI.
    """

    if isinstance(exc, COEApplicationError):
        return exc.message
    return INTERNAL_ERROR_DETAIL


def is_expected(exc: BaseException) -> bool:
    """Return whether the exception is a modelled failure rather than a defect.

    Decides log severity: expected failures are warnings, everything else is an
    error with a traceback.
    """

    return isinstance(exc, COEApplicationError)
