"""SQLAlchemy declarative base for evaluation persistence."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

EVALUATION_SCHEMA = "evaluation"


class Base(DeclarativeBase):
    """Base class for evaluation-owned PostgreSQL tables."""

    metadata = MetaData(schema=EVALUATION_SCHEMA)
