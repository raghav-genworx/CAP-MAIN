"""PostgreSQL database client and session setup."""

from collections.abc import Generator
from functools import lru_cache

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
    """Return the process-wide session factory for this database URL."""

    return session_factory_for_url(settings.database_url)


@lru_cache(maxsize=8)
def session_factory_for_url(database_url: str) -> sessionmaker[Session]:
    """Return the process-wide session factory for an explicit database URL.

    The evaluation repository is constructed from a URL rather than ``Settings``,
    so it enters here. Sharing this cache means core and evaluation use one engine
    and one pool per URL instead of opening a second pool to the same database.
    """

    return sessionmaker(
        bind=create_engine(database_url, pool_pre_ping=True, future=True),
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
