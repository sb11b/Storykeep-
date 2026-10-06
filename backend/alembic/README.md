# Alembic migrations for Storykeep-

Schema migrations are managed with [Alembic](https://alembic.sqlalchemy.org/).
The migration configuration lives in `backend/alembic.ini` and the migration
scripts in `backend/alembic/versions/`.

## Setup

Alembic is listed in `backend/requirements.txt`. Install it alongside the
rest of the backend dependencies:

```bash
cd backend
pip install -r requirements.txt
```

The `DATABASE_URL` is resolved at runtime from `app.config.settings` (which
reads the `DATABASE_URL` environment variable, with the same `postgres://`
→ `postgresql+psycopg2://` normalisation the FastAPI app applies). No
credentials are hard-coded in `alembic.ini`.

## Usage

All commands are run from the `backend/` directory:

```bash
# Apply all pending migrations to the current DATABASE_URL
alembic upgrade head

# Create a new (empty) migration
alembic revision -m "add foo column to users"

# Create a migration by introspecting the SQLAlchemy models (autogenerate)
alembic revision -m "describe the schema change" --autogenerate

# Roll back one revision
alembic downgrade -1

# Show current revision
alembic current

# Show migration history
alembic history --verbose
```

## How it works

`alembic/env.py` imports `app.database.Base` and `app.models`, which
registers every mapped table on `Base.metadata`. Alembic's `--autogenerate`
compares that metadata against the live database and emits `op.create_table`
/ `op.add_column` / etc. calls into a new revision script.

## Relationship to `_create_schema()`

`backend/app/main.py` still contains `_create_schema()`, ~250 lines of
hand-rolled `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements. That
function is **deprecated** in favour of Alembic but is kept for backward
compatibility with existing Railway deploys that rely on it for bootstrap.
Future schema changes should be made via `alembic revision` — do **not**
add new `_try_sql()` calls to `_create_schema()`.
