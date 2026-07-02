"""Evaluation database engine and schema helpers."""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from data.models.postgres import Base
from data.models.postgres.base import EVALUATION_SCHEMA


def create_database_engine(database_url: str) -> Engine:
    """Create a pooled SQLAlchemy engine."""

    options: dict[str, object] = {
        "pool_pre_ping": True,
        "future": True,
    }
    if database_url.startswith("sqlite"):
        options["poolclass"] = NullPool
    engine = create_engine(database_url, **options)
    if database_url.startswith("sqlite"):
        return engine.execution_options(schema_translate_map={EVALUATION_SCHEMA: None})
    return engine


def create_session_factory(database_url: str) -> sessionmaker[Session]:
    """Create a reusable session factory for repository transactions."""

    return sessionmaker(
        bind=create_database_engine(database_url),
        autoflush=False,
        expire_on_commit=False,
    )


def create_test_schema(database_url: str) -> None:
    """Create tables only for isolated tests; deployments use Alembic."""

    engine = create_database_engine(database_url)
    try:
        Base.metadata.create_all(bind=engine)
    finally:
        engine.dispose()


def database_is_ready(database_url: str) -> bool:
    """Return whether the configured database accepts a simple query."""

    engine: Engine | None = None
    try:
        engine = create_database_engine(database_url)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError:
        return False
    finally:
        if engine is not None:
            engine.dispose()
