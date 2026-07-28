"""Structured logging configuration."""

import logging
import sys

from observability.logging.formatters import TEXT_FORMAT, JsonFormatter

#: Chatty third-party loggers. httpx/httpcore log every outbound request at INFO,
#: which buries application logs given how many adapters this process drives.
_QUIET_LOGGERS = ("httpx", "httpcore", "httpx2", "httpcore2")


def configure_logging(log_level: str, *, json_output: bool = False) -> None:
    """Configure process-wide logging.

    ``json_output`` selects the structured formatter. Callers pass
    ``settings.log_json`` so a developer keeps readable text locally while
    deployments emit one JSON object per line for the log platform to index.
    """

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter() if json_output else logging.Formatter(TEXT_FORMAT)
    )

    root = logging.getLogger()
    root.setLevel(log_level.upper())
    # Replace rather than append: configure_logging runs per application factory,
    # and uvicorn's --reload re-imports the module, so appending would duplicate
    # every line once per reload.
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)

    for logger_name in _QUIET_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
