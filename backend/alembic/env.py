"""Alembic environment wired to SQLModel metadata.

Model modules are imported for their side effect of registering tables on
``SQLModel.metadata``. Stage 2 adds them; Stage 1 has an empty metadata object,
which makes ``alembic upgrade head`` a successful no-op.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

import app.models  # noqa: F401  (registers table classes)
from alembic import context
from app.core.config import get_settings

config = context.config

if config.config_file_name is not None:
    # Alembic's config declares only its own loggers. The default
    # ``disable_existing_loggers=True`` would silence application loggers for
    # the rest of the process (tests import the app before running Alembic).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

settings = get_settings()
# `%` must be escaped for ConfigParser interpolation.
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Run migrations without a DB connection (emit SQL)."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
