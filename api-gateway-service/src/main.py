"""Application entry point for the API Gateway Service."""

from api.rest.app import create_app

app = create_app()
