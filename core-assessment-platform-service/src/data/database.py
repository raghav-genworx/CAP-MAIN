"""Backward-compatible imports for the PostgreSQL database client."""

from data.clients.database import (
    create_database_engine,
    create_session_factory,
    database_is_ready,
    session_dependency,
)

__all__ = [
    "create_database_engine",
    "create_session_factory",
    "database_is_ready",
    "session_dependency",
]
