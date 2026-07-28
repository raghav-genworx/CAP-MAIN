"""Serve the browser-facing ``/api/v1/core`` prefix from this application.

The SPA has always addressed the backend as ``/api/v1/core/<path>``: the gateway
owned the ``core`` segment, stripped it, and proxied the rest. With the gateway
folded in, this application answers on both prefixes -- ``/api/v1/core/...`` for
the browser and ``/api/v1/...`` for anything internal.

Implemented as pure ASGI rather than ``@app.middleware("http")`` because the
rewrite has to happen *before* routing. Starlette resolves the route from
``scope["path"]``, so a BaseHTTPMiddleware running after that would be too late.

Why rewrite instead of mounting every router twice: mounting duplicates each
operation in the OpenAPI document, gives every route a second operation ID, and
leaves two definitions to keep in step. One rewrite keeps a single source of truth.
"""

from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


class BrowserPrefixMiddleware:
    """Strip the browser-facing prefix segment before routing."""

    def __init__(self, app: ASGIApp, *, api_prefix: str, segment: str) -> None:
        """Rewrite ``{api_prefix}/{segment}/...`` to ``{api_prefix}/...``."""

        self._app = app
        self._browser_prefix = f"{api_prefix.rstrip('/')}/{segment.strip('/')}"
        self._api_prefix = api_prefix.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Rewrite the path when it carries the browser prefix, then delegate."""

        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path == self._browser_prefix or path.startswith(f"{self._browser_prefix}/"):
            remainder = path[len(self._browser_prefix) :]
            rewritten = f"{self._api_prefix}{remainder}"
            # Copy: the caller's scope may be reused, and mutating it in place has
            # bitten enough ASGI stacks to be worth avoiding.
            scope = dict(scope)
            scope["path"] = rewritten
            # raw_path is bytes and is what some servers echo back; keep the two
            # consistent or a later consumer sees the pre-rewrite value.
            if scope.get("raw_path"):
                scope["raw_path"] = rewritten.encode("ascii")

        await self._app(scope, receive, send)
