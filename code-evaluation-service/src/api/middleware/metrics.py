"""Prometheus metrics endpoint setup."""

from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response


def setup_metrics(app: FastAPI) -> None:
    """Expose Prometheus metrics."""

    @app.get(
        "/metrics",
        include_in_schema=False,
        response_class=Response,
    )
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
