"""Structured logging configuration."""

import logging


def configure_logging(log_level: str) -> None:
    """Configure process-wide structured logging."""

    logging.basicConfig(
        level=log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    for logger_name in ("httpx", "httpcore", "httpx2", "httpcore2"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
