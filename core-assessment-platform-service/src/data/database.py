"""PostgreSQL database setup."""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import Settings


def create_database_engine(settings: Settings) -> Engine:
    """Create the SQLAlchemy engine."""

    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        future=True,
    )


def create_session_factory(settings: Settings) -> sessionmaker[Session]:
    """Create a configured SQLAlchemy session factory."""

    return sessionmaker(
        bind=create_database_engine(settings),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def database_is_ready(settings: Settings) -> bool:
    """Return whether PostgreSQL accepts a lightweight readiness query."""

    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        engine.dispose()


def session_dependency(settings: Settings) -> Generator[Session, None, None]:
    """Yield a request-scoped database session."""

    session_factory = create_session_factory(settings)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
