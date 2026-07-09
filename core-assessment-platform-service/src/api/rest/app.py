"""FastAPI application factory."""

from typing import Any, cast

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.middleware.cors import setup_cors
from api.middleware.error_handler import setup_error_handlers
from api.middleware.logging import setup_request_logging
from api.middleware.metrics import setup_metrics
from api.rate_limit import limiter
from api.rest.routes import (
    assessments,
    auth,
    candidate_portal,
    health,
    notifications,
    question_bank,
)
from config.settings import get_settings
from observability.logging.config import configure_logging


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        description="COE-compliant FastAPI service.",
        version="0.1.0",
    )
    app.state.limiter = limiter
    app.add_exception_handler(
        RateLimitExceeded,
        cast(Any, _rate_limit_exceeded_handler),
    )
    app.add_middleware(SlowAPIMiddleware)

    setup_error_handlers(app)
    setup_request_logging(app)
    setup_cors(app, settings)
    setup_metrics(app)

    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(assessments.router, prefix=settings.api_prefix)
    app.include_router(candidate_portal.router, prefix=settings.api_prefix)
    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(notifications.router, prefix=settings.api_prefix)
    app.include_router(question_bank.router, prefix=settings.api_prefix)
    return app
