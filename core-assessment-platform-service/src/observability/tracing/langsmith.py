"""LangSmith tracing helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Literal

from langsmith import Client
from langsmith.run_helpers import trace, tracing_context
from langsmith.run_trees import RunTree

from config.settings import Settings

LOGGER = logging.getLogger(__name__)
LangSmithRunType = Literal[
    "tool",
    "chain",
    "llm",
    "retriever",
    "embedding",
    "prompt",
    "parser",
]


def langsmith_enabled(settings: Settings) -> bool:
    """Return whether LangSmith tracing should be activated."""

    return bool(settings.langsmith_tracing and settings.langsmith_api_key.strip())


@lru_cache(maxsize=4)
def _langsmith_client(api_url: str, api_key: str) -> Client:
    return Client(
        api_url=api_url,
        api_key=api_key,
        tracing_error_callback=_log_tracing_error,
    )


def _log_tracing_error(exc: Exception) -> None:
    LOGGER.warning("LangSmith trace delivery failed: %s", type(exc).__name__)


@contextmanager
def langsmith_run(
    settings: Settings,
    name: str,
    *,
    run_type: LangSmithRunType = "chain",
    inputs: dict[str, Any] | None = None,
    outputs: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    metadata: Mapping[str, Any] | None = None,
    parent: RunTree | Mapping[str, Any] | str | None = None,
) -> Iterator[RunTree | None]:
    """Create a LangSmith run when tracing is configured.

    The context is intentionally no-op unless LANGSMITH_TRACING is enabled and
    LANGSMITH_API_KEY is configured, so local development remains unchanged.
    """

    if not langsmith_enabled(settings):
        if settings.langsmith_tracing:
            LOGGER.warning(
                "LANGSMITH_TRACING is enabled but LANGSMITH_API_KEY is empty; "
                "question generation traces are disabled."
            )
        yield None
        return

    client = _langsmith_client(
        settings.langsmith_endpoint,
        settings.langsmith_api_key.strip(),
    )
    with tracing_context(
        project_name=settings.langsmith_project,
        tags=tags,
        metadata=dict(metadata or {}),
        parent=parent,
        enabled=True,
        client=client,
    ), trace(
        name,
        run_type=run_type,
        inputs=inputs,
        project_name=settings.langsmith_project,
        parent=parent,
        tags=tags,
        metadata=metadata,
        client=client,
    ) as run:
        yield run
        if outputs is not None:
            run.end(outputs=outputs)


__all__ = ["langsmith_enabled", "langsmith_run"]
