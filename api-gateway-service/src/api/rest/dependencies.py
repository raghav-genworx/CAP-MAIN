"""Reusable FastAPI dependencies."""

from collections.abc import Generator

from config.settings import Settings, get_settings
from core.services.gateway_service import GatewayService


def settings_dependency() -> Generator[Settings, None, None]:
    """Yield application settings for request handlers."""

    yield get_settings()


def gateway_service_dependency() -> Generator[GatewayService, None, None]:
    """Yield the gateway service."""

    yield GatewayService(get_settings())
