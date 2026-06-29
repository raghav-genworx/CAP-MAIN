"""Core readiness contract tests."""

import asyncio
from unittest.mock import patch

from fastapi import Response

from api.rest.routes.health import health
from config.settings import Settings


def test_health_is_degraded_when_database_is_unavailable() -> None:
    response = Response()
    with patch("api.rest.routes.health.database_is_ready", return_value=False):
        payload = asyncio.run(health(Settings(), response))

    assert response.status_code == 503
    assert payload.status == "degraded"
