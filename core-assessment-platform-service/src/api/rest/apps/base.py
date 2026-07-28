"""Shared application assembly.

Every application gets the same middleware stack, error envelope, metrics endpoint
and rate limiter. Only the routers differ. This replaces four byte-identical
``create_app`` implementations, one per service.
"""

from collections.abc import Sequence
from typing import Any, cast

from fastapi import APIRouter, FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from api.middleware.browser_prefix import BrowserPrefixMiddleware
from api.middleware.cors import setup_cors
from api.middleware.error_handler import setup_error_handlers
from api.middleware.logging import setup_request_logging
from api.middleware.metrics import setup_metrics
from api.rate_limit import limiter as shared_limiter
from config.settings import get_settings
from observability.logging.logger import configure_logging


def build_app(
    *,
    routers: Sequence[APIRouter],
    app_name: str = "core",
    limiter: Limiter | None = None,
    browser_prefix_segment: str | None = None,
) -> FastAPI:
    """Assemble an application from ``routers``.

    ``limiter`` defaults to the shared limiter declared in ``api.rate_limit``, which
    the candidate portal's per-route decorators are bound to. An application with no
    decorated routes may pass its own.
    """

    settings = get_settings()
    configure_logging(settings.log_level, json_output=settings.log_json)

    app = FastAPI(
        title=settings.app_name,
        description="COE-compliant FastAPI service.",
        version="0.1.0",
    )
    app.state.limiter = limiter or shared_limiter
    app.add_exception_handler(
        RateLimitExceeded,
        cast(Any, _rate_limit_exceeded_handler),
    )
    app.add_middleware(SlowAPIMiddleware)

    setup_error_handlers(app)
    setup_request_logging(app, app_name=app_name)
    setup_cors(app, settings)
    setup_metrics(app)

    for router in routers:
        app.include_router(router, prefix=settings.api_prefix)

    if browser_prefix_segment:
        # Outermost, so the path is rewritten before Starlette routes it and
        # before every other middleware sees it -- logging and metrics then
        # record the canonical path rather than two spellings of it.
        app.add_middleware(
            BrowserPrefixMiddleware,
            api_prefix=settings.api_prefix,
            segment=browser_prefix_segment,
        )

    return app


def default_limiter() -> Limiter:
    """Return a limiter matching what the non-core services declared inline."""

    return Limiter(key_func=get_remote_address, default_limits=["120/minute"])
