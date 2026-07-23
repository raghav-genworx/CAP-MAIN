"""Backward-compatible imports for the evaluation database client."""

from data.clients.database import (
    create_database_engine,
    create_session_factory,
    create_test_schema,
    database_is_ready,
)

__all__ = [
    "create_database_engine",
    "create_session_factory",
    "create_test_schema",
    "database_is_ready",
]
