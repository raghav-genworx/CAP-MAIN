"""The code execution application.

A trusted, backend-only Judge0 adapter. Candidate code is compiled and run inside
an isolated Judge0 deployment, never in this process -- this application only
submits work to it and normalises the result.

Phase 4 removes the HTTP surface entirely and calls the service in-process, at
which point this factory exists solely as the extraction seam.
"""

from fastapi import FastAPI

from api.rest.apps.base import build_app, default_limiter
from api.rest.routes import executions
from api.rest.routes.health import build_health_router
from config.settings import Settings
from core.exceptions.execution import Judge0ServiceError
from core.services.execution.code_execution_service import CodeExecutionService


async def judge0_ready(settings: Settings) -> bool:
    """Report whether the configured Judge0 deployment answers a language query."""

    try:
        return bool(await CodeExecutionService(settings).get_languages())
    except Judge0ServiceError:
        return False


def create_app() -> FastAPI:
    """Create the code execution application."""

    return build_app(
        app_name="execution",
        routers=[
            executions.router,
            build_health_router(
                distribution="code-execution-service",
                probe=judge0_ready,
            ),
        ],
        limiter=default_limiter(),
    )
