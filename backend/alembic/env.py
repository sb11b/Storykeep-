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
from sqlalchemy import create_engine, pool

# Ensure the backend/ directory (which contains the ``app`` package) is on
# sys.path regardless of where alembic is invoked from.  ``__file__`` is
# backend/alembic/env.py, so the parent of this file's directory is backend/.
# Without this, the documented ``cd backend; alembic upgrade head`` path would
# add backend/alembic (which has no ``app`` package) and the app.config import
# below would fail with ModuleNotFoundError.
_backend_dir = Path(__file__).resolve().parent.parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from app.config import settings  # noqa: E402
from app.database import Base, db_connect  # noqa: E402
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

    The baseline revision (0001) cannot produce SQL in offline mode because
    it bootstraps the schema via ``Base.metadata.create_all`` which requires
    a live connection. Reject offline generation for that revision.
    """
    # Reject offline generation for the baseline before dispatching any
    # revision. The baseline uses Base.metadata.create_all which requires
    # a live database connection and cannot produce SQL.
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    # Reject offline generation for the baseline before dispatching any
    # revision. The baseline uses Base.metadata.create_all which requires
    # a live database connection and cannot produce SQL.
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(config)
    head_revision = script.get_current_head()
    if head_revision == "0001_initial_schema":
        raise RuntimeError(
            "Offline SQL generation is not supported for the baseline revision "
            "(0001_initial_schema) because it bootstraps the schema via "
            "Base.metadata.create_all which requires a live database connection. "
            "Run 'alembic upgrade head' against a live database instead."
        )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Builds an engine using the same ``db_connect`` the FastAPI app uses, so
    the sslmode normalization (dropping verify-full, using require for public
    hosts) is applied identically. We do NOT reuse ``app.database.engine``
    because Alembic manages its own connection pool lifecycle and should not
    close the app's long-lived engine when the migration run finishes.
    """
    connectable = create_engine(
        db_connect.url,
        connect_args=db_connect.connect_args,
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
