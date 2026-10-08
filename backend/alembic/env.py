"""Alembic environment for Storykeep-.

This module wires Alembic to the existing SQLAlchemy engine and metadata
defined in ``app.database`` and ``app.models``. The DATABASE_URL is resolved
at runtime from ``app.config.settings`` (which reads the ``DATABASE_URL``
environment variable, with the same normalisation the FastAPI app uses), so
no credentials are hard-coded here.

Run from ``backend/``::

    alembic upgrade head
    alembic revision -m "describe the change"
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Ensure the backend/ directory (which contains the ``app`` package) is on
# sys.path regardless of where alembic is invoked from.  When running
# ``alembic`` from inside ``backend/`` this is a no-op; when running from
# the repo root it lets ``import app`` resolve correctly.
_backend_dir = Path(__file__).resolve().parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from app.config import settings  # noqa: E402
from app.database import Base  # noqa: E402
import app.models  # noqa: F401, E402  — registers all models on Base.metadata

# this is the Alembic Config object
config = context.config

# Interpret the config file for Python logging, if present.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve the target metadata from the app's declarative Base.  Importing
# ``app.models`` above has registered every mapped table on ``Base.metadata``,
# so autogenerate will see the full schema.
target_metadata = Base.metadata

# Override the placeholder sqlalchemy.url in alembic.ini with the real
# runtime value from app.config.settings.  This reuses the same URL
# normalisation (postgres:// → postgresql+psycopg2://) the app applies.
# Escape % as %%: ConfigParser treats % as interpolation, so a
# percent-encoded password character would break the assignment before the
# migration ever connects. Alembic documents this requirement for
# set_main_option.
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This emits SQL to stdout rather than connecting to a live database.
    Useful for generating SQL scripts for review or for environments where
    a direct DB connection is not available.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an Engine and associates a connection with the migration context.
    The connection is retrieved from the same ``app.database`` module the
    FastAPI app uses, so the session/timeout options stay consistent.
    """
    # Build a fresh engine from the alembic.ini + overridden URL.  We do NOT
    # reuse ``app.database.engine`` here because Alembic manages its own
    # connection pool lifecycle and should not close the app's long-lived
    # engine when the migration run finishes.
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
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
