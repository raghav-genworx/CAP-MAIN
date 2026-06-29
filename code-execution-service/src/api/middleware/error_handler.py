"""Application error handlers."""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.middleware.logging import get_request_id
from core.exceptions.base import COEApplicationError

logger = logging.getLogger(__name__)


def _safe_validation_errors(exc: RequestValidationError) -> list[dict[str, object]]:
    """Return actionable validation details without echoing request values."""

    return [
        {
            key: value
            for key, value in error.items()
            if key not in {"input", "ctx", "url"}
        }
        for error in exc.errors()
    ]


def setup_error_handlers(app: FastAPI) -> None:
    """Register JSON error handlers for expected and unexpected failures."""

    @app.exception_handler(COEApplicationError)
    async def coe_error_handler(
        request: Request,
        exc: COEApplicationError,
    ) -> JSONResponse:
        request_id = get_request_id(request)
        logger.warning(
            "application_error request_id=%s path=%s message=%s",
            request_id,
            request.url.path,
            exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "trace_id": request_id},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        request_id = get_request_id(request)
        safe_errors = _safe_validation_errors(exc)
        logger.warning(
            "validation_error request_id=%s path=%s errors=%s",
            request_id,
            request.url.path,
            safe_errors,
        )
        return JSONResponse(
            status_code=422,
            content={
                "detail": jsonable_encoder(safe_errors),
                "trace_id": request_id,
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        request_id = get_request_id(request)
        logger.exception(
            "unexpected_error request_id=%s path=%s",
            request_id,
            request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "trace_id": request_id},
        )
