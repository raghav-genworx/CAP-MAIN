"""FastAPI application factory.

Retained so ``main:app`` -- the entry point Compose and Cloud Run both invoke --
keeps resolving while the four applications move under ``api.rest.apps``.
"""

from fastapi import FastAPI

from api.rest.apps.core import create_app as create_core_app


def create_app() -> FastAPI:
    """Create the core platform application."""

    return create_core_app()
