"""CORS middleware setup."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import Settings


def setup_cors(app: FastAPI, settings: Settings) -> None:
    """Install CORS middleware using environment-driven origins."""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
