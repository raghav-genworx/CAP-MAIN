"""SQLAlchemy declarative base for evaluation persistence."""

import os

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

EVALUATION_SCHEMA = (
    os.getenv("EVALUATION_DB_SCHEMA", "evaluation").strip() or "evaluation"
)


class Base(DeclarativeBase):
    """Base class for evaluation-owned PostgreSQL tables."""

    metadata = MetaData(schema=EVALUATION_SCHEMA)
