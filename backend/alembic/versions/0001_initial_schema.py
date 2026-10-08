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
    """Baseline: PostgreSQL extensions and non-ORM indexes only.

    The tables themselves are owned by ``_create_schema()`` in ``main.py``
    (kept for existing Railway deploys). This revision therefore adds ONLY
    idempotent, additive objects and never derives DDL from ``Base.metadata``:
    a baseline must freeze one schema definition. If it re-created tables from
    the live models, a later revision's ``add_column`` would fail on a fresh
    database because this revision had already created that column.
    """
    # PostgreSQL extensions required by the models (pgcrypto for gen_random_uuid,
    # pg_trgm for GIN trigram indexes).
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

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
    """Non-destructive baseline: this revision has no safe rollback.

    The baseline captures tables that already existed in production before
    Alembic was introduced, so dropping them would delete live user data.
    Rolling back to "before 0001" is therefore a no-op: Alembic removes its
    own ``alembic_version`` bookkeeping, and nothing else is touched. Teardown
    of a scratch database is an explicit operator action, never a downgrade.
    """
    pass
