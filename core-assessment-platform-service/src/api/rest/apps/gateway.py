"""The edge gateway application.

Authenticates browser traffic and reverse-proxies it to a registered upstream. It
is the only application the browser reaches directly.

Phase 5 folds this into the core application: the route policy becomes FastAPI
dependencies and the proxy disappears, since core will serve the browser-facing
``/api/v1/core`` prefix itself.
"""

from fastapi import FastAPI

from api.rest.apps.base import build_app, default_limiter
from api.rest.routes import gateway, gateway_auth, proxy
from api.rest.routes.health import always_ready, build_health_router


def create_app() -> FastAPI:
    """Create the edge gateway application."""

    return build_app(
        app_name="gateway",
        routers=[
            gateway_auth.router,
            gateway.router,
            # The catch-all proxy must be registered last so the concrete routes
            # above are matched first.
            build_health_router(
                distribution="api-gateway-service",
                probe=always_ready,
            ),
            proxy.router,
        ],
        limiter=default_limiter(),
    )
