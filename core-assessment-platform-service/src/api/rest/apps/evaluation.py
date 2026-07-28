"""The code evaluation application.

Scores final submissions from hidden execution evidence, ranks candidates, and
generates PDF reports. Backend-only: no browser ever reaches these routes.

Phase 4 removes the HTTP surface and calls the service in-process, leaving this
factory as the extraction seam.
"""

from fastapi import FastAPI

from api.rest.apps.base import build_app, default_limiter
from api.rest.routes import evaluations
from api.rest.routes.health import build_health_router, postgres_ready


def create_app() -> FastAPI:
    """Create the code evaluation application."""

    return build_app(
        app_name="evaluation",
        routers=[
            evaluations.router,
            build_health_router(
                distribution="code-evaluation-service",
                probe=postgres_ready,
            ),
        ],
        limiter=default_limiter(),
    )
