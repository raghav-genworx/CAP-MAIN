"""SQLAlchemy declarative base for evaluation persistence."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for evaluation-owned PostgreSQL tables."""
