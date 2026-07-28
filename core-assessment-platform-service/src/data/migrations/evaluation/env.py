"""Alembic environment for evaluation-owned PostgreSQL tables."""

from collections.abc import MutableMapping
from logging.config import fileConfig
from typing import Literal

from sqlalchemy import engine_from_config, pool, text

from alembic import context
from config.settings import get_settings
from data.models.postgres.base import EVALUATION_METADATA_SCHEMA, EVALUATION_SCHEMA
from data.models.postgres.evaluation import EvaluationBase

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = EvaluationBase.metadata

#: Evaluation owns these tables. Scoping by name rather than by schema is what makes
#: the filter correct when ``EVALUATION_DB_SCHEMA=public`` -- see below.
EVALUATION_TABLE_NAMES = frozenset(
    table.name for table in target_metadata.tables.values()
) | {"evaluation_alembic_version"}


def should_create_schema() -> bool:
    """Return whether migrations should create the configured schema."""

    return EVALUATION_SCHEMA != "public"


def include_evaluation_objects(
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
    """Keep autogeneration scoped to evaluation-owned database objects.

    Previously this compared ``parent_names["schema_name"]`` against
    ``EVALUATION_SCHEMA``. That works for a dedicated schema, but Compose and the
    Cloud Run deploy script both set ``EVALUATION_DB_SCHEMA=public``, and reflection
    reports the default schema as ``None``. Every evaluation table was therefore
    filtered out of the reflected side while remaining on the metadata side, so
    ``alembic check`` reported the whole schema as pending creation. CI never caught
    it because its job leaves the variable unset and gets the ``evaluation`` default.

    Scoping by table name is correct under either setting and mirrors
    ``include_core_objects`` in the core tree, which has to scope by name for the
    same reason: with both trees in ``public``, schema alone cannot tell them apart.
    """

    # Compare against the normalised value: with include_schemas=True Alembic
    # presents the connection's default schema as None, so testing against the
    # literal "public" rejects the whole schema and nothing gets reflected.
    if type_ == "schema":
        return name == EVALUATION_METADATA_SCHEMA
    if type_ == "table":
        return name in EVALUATION_TABLE_NAMES
    return True


def run_migrations_offline() -> None:
    """Run migrations without opening a database connection."""

    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_schemas=True,
        include_name=include_evaluation_objects,
        version_table="evaluation_alembic_version",
        version_table_schema=EVALUATION_METADATA_SCHEMA,
    )
    if should_create_schema():
        try:
            context.execute(f'CREATE SCHEMA IF NOT EXISTS "{EVALUATION_SCHEMA}"')
        except Exception as e:
            print(f"Skipping schema creation in offline mode: {e}")
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
        if connection.dialect.name == "postgresql" and should_create_schema():
            try:
                connection.execute(
                    text(f'CREATE SCHEMA IF NOT EXISTS "{EVALUATION_SCHEMA}"')
                )
                connection.commit()
            except Exception as e:
                connection.rollback()
                print(f"Skipping schema creation: {e}")
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_schemas=True,
            include_name=include_evaluation_objects,
            version_table="evaluation_alembic_version",
            version_table_schema=EVALUATION_METADATA_SCHEMA,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
