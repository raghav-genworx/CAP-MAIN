"""Backward-compatible import for the execution HTTP adapter."""

from typing import Any

from handlers.http_clients import execution as _implementation

ExecutionAdapterService = _implementation.ExecutionAdapterService
_compat: Any = _implementation
httpx = _compat.httpx

__all__ = ["ExecutionAdapterService", "httpx"]
