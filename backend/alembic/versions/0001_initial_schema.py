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

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Baseline: bootstrap the full schema on a fresh database.

    Uses ``Base.metadata.create_all`` via the migration connection so that
    Alembic owns the DDL and any failure propagates (unlike the app's
    ``_create_schema()`` which swallows errors). On an existing database
    ``create_all`` is a no-op. After bootstrap, Alembic owns all future
    schema changes via revisions.
    """
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)


def downgrade() -> None:
    """Non-destructive baseline: this revision has no safe rollback.

    The baseline captures tables that already existed in production before
    Alembic was introduced, so dropping them would delete live user data.
    Rolling back to "before 0001" is therefore a no-op: Alembic removes its
    own ``alembic_version`` bookkeeping, and nothing else is touched. Teardown
    of a scratch database is an explicit operator action, never a downgrade.
    """
    pass
