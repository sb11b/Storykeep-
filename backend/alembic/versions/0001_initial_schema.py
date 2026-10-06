"""initial schema baseline from SQLAlchemy models

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-06 00:00:00.000000

This is the initial Alembic migration for Storykeep-.  It captures the
current schema state as defined by the SQLAlchemy models in ``app.models``.

On a fresh database this migration creates every table, index and constraint
declared by the ORM.  On an existing database (already bootstrapped by
``_create_schema()`` in ``main.py``) every object already exists, so
``create_all`` is a no-op — only the ``alembic_version`` table is new.

``_create_schema()`` is kept for backward compatibility with existing
Railway deploys; future schema changes should go through Alembic revisions
instead of adding more ``_try_sql()`` calls.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the full schema from the SQLAlchemy metadata.

    Using ``Base.metadata.create_all`` (via the bind) is idempotent: on a
    fresh database it creates every table, on an existing database it
    skips objects that already exist.  This is the safest baseline for an
    app that previously managed its own schema with hand-rolled DDL.
    """
    # Import the app's Base after Alembic has established the migration
    # connection so create_all binds to the correct connection.
    from app.database import Base
    import app.models  # noqa: F401 — registers all tables on Base.metadata

    bind = op.get_bind()
    # PostgreSQL extensions required by the models (pgcrypto for gen_random_uuid,
    # pg_trgm for GIN trigram indexes).
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    Base.metadata.create_all(bind=bind)

    # Additional indexes that _create_schema() created outside of the ORM
    # models.  These are idempotent (IF NOT EXISTS) so they are safe to run
    # on both fresh and existing databases.
    op.execute(
        "CREATE INDEX IF NOT EXISTS articles_search_idx "
        "ON articles USING GIN (search_vector)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS change_log_user_cursor_idx "
        "ON change_log (user_id, id)"
    )


def downgrade() -> None:
    """Drop all tables created by the initial schema.

    Downgrading the baseline is destructive and not expected in production.
    It is provided for completeness and local-dev teardown only.
    """
    from app.database import Base
    import app.models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
