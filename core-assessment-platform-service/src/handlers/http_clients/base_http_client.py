"""Shared behaviour for outbound HTTP adapters.

Before consolidation there were eight hand-rolled clients across four services,
each with its own timeout handling, its own (or no) retry policy, and its own
logging. This is the one place that behaviour is defined.

Two deliberate choices:

**A client per call, not a pooled one.** Pooling would be faster, but an
``httpx.AsyncClient`` binds its connection pool to the event loop that first uses
it, and ``run_async`` may run on the host loop or on a loop it creates for the
call. A cached client would eventually be reused across loops and fail. Pooling
becomes correct once the service layer is async and there is exactly one loop --
that is the follow-up to this phase, not part of it.

**Retries are opt in.** Several adapters POST work that creates rows -- an
evaluation job, an invite email. Retrying those on a transport error risks doing
the thing twice, and none of them are idempotent. Only callers that know a request
is safe to repeat ask for retries.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

#: Transport-level failures: connection refused, DNS, read timeout. A retry can
#: plausibly succeed. Deliberately excludes HTTPStatusError -- a 4xx will not
#: change, and a 5xx may well have applied a side effect already.
RETRYABLE_EXCEPTIONS = (httpx.TransportError,)


class BaseHttpClient:
    """Base class for outbound HTTP adapters."""

    #: Used in log lines to identify the upstream.
    service_name: str = "upstream"

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        headers: dict[str, str] | None = None,
        service_name: str | None = None,
    ) -> None:
        """Configure the adapter's upstream, timeout and static headers."""

        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._headers = headers or {}
        if service_name is not None:
            self.service_name = service_name

    def url_for(self, path: str) -> str:
        """Return the absolute URL for an upstream path."""

        return f"{self._base_url}/{path.lstrip('/')}"

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        retry_attempts: int = 1,
        timeout_seconds: float | None = None,
    ) -> httpx.Response:
        """Send a request and return the response.

        Args:
            retry_attempts: Total attempts, including the first. Leave at 1 unless
                the request is safe to repeat.

        Raises:
            httpx.HTTPError: on transport failure, or a non-2xx response. Callers
                translate this into their own domain error.
        """

        url = self.url_for(path)
        timeout = timeout_seconds or self._timeout_seconds

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max(1, retry_attempts)),
            wait=wait_exponential(multiplier=0.5, max=8),
            retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
            reraise=True,
        ):
            with attempt:
                async with httpx.AsyncClient(
                    timeout=timeout,
                    headers=self._headers,
                ) as client:
                    response = await client.request(method, url, json=json)
                    self._log_result(method, path, response)
                    response.raise_for_status()
                    return response

        # AsyncRetrying with reraise=True either returns above or raises.
        raise AssertionError("unreachable")

    def _log_result(
        self,
        method: str,
        path: str,
        response: httpx.Response,
    ) -> None:
        """Log the outcome without ever emitting request or response bodies.

        Payloads on these routes carry candidate source code and hidden test
        cases; neither belongs in application logs.
        """

        if response.is_error:
            logger.error(
                "upstream_error service=%s method=%s path=%s status_code=%s",
                self.service_name,
                method,
                path,
                response.status_code,
            )
        else:
            logger.debug(
                "upstream_ok service=%s method=%s path=%s status_code=%s",
                self.service_name,
                method,
                path,
                response.status_code,
            )
