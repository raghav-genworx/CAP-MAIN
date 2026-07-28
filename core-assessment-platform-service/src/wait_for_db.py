"""Block until PostgreSQL accepts connections.

Compose's ``depends_on: condition: service_healthy`` only works inside one
project. With infrastructure, backend and frontend split into independent
projects, the migration job can no longer wait on the database that way -- and
without a wait it races a starting PostgreSQL, which is exactly the failure that
took the whole stack down after an unclean shutdown ("the database system is not
yet accepting connections", during crash recovery).

    python -m wait_for_db && alembic -c alembic.ini upgrade head
"""

from __future__ import annotations

import sys
import time

import psycopg

from config.settings import get_settings

#: Long enough to cover PostgreSQL crash recovery on a large volume, short enough
#: that a genuinely unreachable database fails the deploy rather than hanging.
TIMEOUT_SECONDS = 180.0
RETRY_INTERVAL_SECONDS = 2.0


def _libpq_url(database_url: str) -> str:
    """Return the SQLAlchemy URL in the form libpq accepts."""

    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


def wait_for_database(
    *,
    timeout_seconds: float = TIMEOUT_SECONDS,
    retry_interval_seconds: float = RETRY_INTERVAL_SECONDS,
) -> bool:
    """Return whether the database became reachable within the timeout."""

    url = _libpq_url(get_settings().database_url)
    deadline = time.monotonic() + timeout_seconds
    attempt = 0

    while True:
        attempt += 1
        try:
            psycopg.connect(url, connect_timeout=3).close()
            print(f"database ready after {attempt} attempt(s)", flush=True)
            return True
        except Exception as exc:
            if time.monotonic() >= deadline:
                print(f"database unreachable after {timeout_seconds}s: {exc}", flush=True)
                return False
            # One line per attempt, not per second: this is read from container
            # logs when a deploy looks stuck.
            print(f"waiting for database (attempt {attempt}): {exc}", flush=True)
            time.sleep(retry_interval_seconds)


def main() -> None:
    """Exit 0 once the database is reachable, non-zero on timeout."""

    sys.exit(0 if wait_for_database() else 1)


if __name__ == "__main__":
    main()
