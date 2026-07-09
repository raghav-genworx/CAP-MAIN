"""Backward-compatible module alias for the AI HTTP gateway."""

import sys

from handlers.http_clients import ai_gateway as _implementation

AIGatewayService = _implementation.AIGatewayService
_AIProviderTarget = _implementation._AIProviderTarget

__all__ = ["AIGatewayService", "_AIProviderTarget"]

sys.modules[__name__] = _implementation
