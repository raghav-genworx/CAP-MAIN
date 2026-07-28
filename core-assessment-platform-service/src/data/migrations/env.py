"""Alembic environment for core-owned PostgreSQL tables."""

from collections.abc import MutableMapping
from logging.config import fileConfig
from typing import Literal

from sqlalchemy import engine_from_config, pool

from alembic import context
from config.settings import get_settings
from data.models.postgres import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata

#: Core owns these tables. Everything else in the database belongs to another
#: migration tree and must be invisible to core's autogenerate.
CORE_TABLE_NAMES = frozenset(target_metadata.tables) | {"alembic_version"}


def include_core_objects(
    name: str | None,
    type_: Literal[
        "schema",
        "table",
        "column",
        "index",
        "unique_constraint",
        "foreign_key_constraint",
    ],
    parent_names: MutableMapping[
        Literal["schema_name", "table_name", "schema_qualified_table_name"],
        str | None,
    ],
) -> bool:
    """Keep autogeneration scoped to core-owned database objects.

    The evaluation migration tree shares this database and, with
    ``EVALUATION_DB_SCHEMA=public`` (what both Compose and Cloud Run set), shares the
    schema too. Without this filter core's ``alembic check`` reports
    ``evaluation_jobs``, ``assessment_reports`` and ``evaluation_alembic_version`` as
    tables to drop, because they are absent from core's metadata. That is mirrored by
    ``include_evaluation_objects`` in the evaluation tree, which scopes itself by
    schema; core cannot do the same when both live in ``public``, so it scopes by name.

    Trade-off, identical to the one the evaluation tree already accepts: a core table
    deleted from the models is no longer reported as a pending drop. Removals must be
    written by hand.
    """

    if type_ == "table":
        return name in CORE_TABLE_NAMES
    return True


def run_migrations_offline() -> None:
    """Run migrations without opening a database connection."""

    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_server_default=True,
        compare_type=True,
        include_name=include_core_objects,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the configured database."""

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_server_default=True,
            compare_type=True,
            include_name=include_core_objects,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
