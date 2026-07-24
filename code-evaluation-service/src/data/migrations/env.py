"""Alembic environment for evaluation-owned PostgreSQL tables."""

from collections.abc import MutableMapping
from logging.config import fileConfig
from typing import Literal

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from config.settings import get_settings
from data.models.postgres import Base
from data.models.postgres.base import EVALUATION_SCHEMA

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


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
    """Keep autogeneration scoped to evaluation-owned database objects."""

    if type_ == "schema":
        return name == EVALUATION_SCHEMA
    if type_ == "table":
        return parent_names.get("schema_name") == EVALUATION_SCHEMA
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
        version_table_schema=EVALUATION_SCHEMA,
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
            version_table_schema=EVALUATION_SCHEMA,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
