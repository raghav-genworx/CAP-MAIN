"""The core platform application.

Serves the recruiter and candidate surfaces the browser reaches through the
gateway: assessments, question bank, candidate portal, notifications and auth.
"""

from fastapi import FastAPI

from api.rest.apps.base import build_app
from api.rest.routes import (
    assessments,
    auth,
    candidate_portal,
    notifications,
    question_bank,
)
from api.rest.routes.health import build_health_router, postgres_ready


def create_app() -> FastAPI:
    """Create the core platform application."""

    return build_app(
        app_name="core",
        # The SPA addresses this application as /api/v1/core/... -- the segment
        # the gateway used to own and strip.
        browser_prefix_segment="core",
        routers=[
            auth.router,
            assessments.router,
            candidate_portal.router,
            build_health_router(probe=postgres_ready),
            notifications.router,
            question_bank.router,
        ],
    )
