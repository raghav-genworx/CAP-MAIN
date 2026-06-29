"""Request logging middleware."""

import logging
import re
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def get_request_id(request: Request) -> str:
    """Return the request correlation ID assigned by the logging middleware."""

    return str(getattr(request.state, "request_id", "unknown"))


def _request_id_from(request: Request) -> str:
    supplied = request.headers.get(REQUEST_ID_HEADER, "")
    return supplied if _SAFE_REQUEST_ID.fullmatch(supplied) else uuid4().hex


def setup_request_logging(app: FastAPI) -> None:
    """Install structured request logging middleware."""

    @app.middleware("http")
    async def log_request(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = _request_id_from(request)
        request.state.request_id = request_id
        started_at = time.perf_counter()
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        duration_ms = (time.perf_counter() - started_at) * 1000
        logger.info(
            "http_request request_id=%s method=%s path=%s status_code=%s "
            "duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
