"""Shared repository primitives for SQLAlchemy-backed data access."""

from sqlalchemy.orm import Session


class BaseRepository:
    """Base repository with common unit-of-work operations."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, instance: object) -> None:
        """Stage a model instance for persistence."""

        self._session.add(instance)

    def delete(self, instance: object) -> None:
        """Stage a model instance for deletion."""

        self._session.delete(instance)

    def flush(self) -> None:
        """Flush pending changes to the database transaction."""

        self._session.flush()

    def commit(self) -> None:
        """Commit the current database transaction."""

        self._session.commit()

    def rollback(self) -> None:
        """Roll back the current database transaction."""

        self._session.rollback()

    def refresh(self, instance: object) -> None:
        """Refresh a model instance from the database."""

        self._session.refresh(instance)

    def expire_all(self) -> None:
        """Expire cached ORM state so subsequent reads observe external commits."""

        self._session.expire_all()
