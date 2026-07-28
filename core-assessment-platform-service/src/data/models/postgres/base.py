"""SQLAlchemy declarative bases.

Two independent bases share one database, each owned by its own Alembic tree and
version table. They are deliberately kept apart:

* ``Base`` -- core platform tables in the default schema, versioned by
  ``alembic_version``.
* ``EvaluationBase`` -- evaluation tables in ``EVALUATION_DB_SCHEMA``, versioned by
  ``evaluation_alembic_version``.

Merging them into one ``MetaData`` would make each tree's ``alembic check`` demand
the other's tables be dropped, and would make extracting the evaluation context back
into its own service far harder. Do not add a foreign key between them: evaluation
references core rows by ID string, and that is what keeps the two separable.
"""

import os

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

#: Compose and the Cloud Run deploy script both set this to ``public``, so the two
#: bases usually share a schema and are told apart by table name. Migration scripts
#: pass this to ``op.create_table(..., schema=...)``, so it keeps the literal value.
EVALUATION_SCHEMA = (
    os.getenv("EVALUATION_DB_SCHEMA", "evaluation").strip() or "evaluation"
)

#: The same schema as SQLAlchemy represents it on ``MetaData``.
#:
#: SQLAlchemy and Alembic denote the connection's default schema as ``None``.
#: Declaring ``MetaData(schema="public")`` makes every metadata table compare as
#: ``("public", name)`` against a reflected ``(None, name)``, so autogenerate reports
#: the entire schema as missing and ``alembic check`` fails -- even though the tables
#: exist and the tree is at head. Normalising ``public`` to ``None`` here keeps the
#: two sides comparable while leaving the applied migration history untouched.
EVALUATION_METADATA_SCHEMA: str | None = (
    None if EVALUATION_SCHEMA == "public" else EVALUATION_SCHEMA
)


class Base(DeclarativeBase):
    """Base class for core-owned PostgreSQL models."""


class EvaluationBase(DeclarativeBase):
    """Base class for evaluation-owned PostgreSQL tables."""

    metadata = MetaData(schema=EVALUATION_METADATA_SCHEMA)
