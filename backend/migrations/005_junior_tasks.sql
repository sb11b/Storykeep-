-- Junior tasks — work requests dispatched to machine clients (Hermes).
-- Claim/complete/fail with lease semantics. Apply after 004.
--   psql "$DATABASE_URL" -f backend/migrations/005_junior_tasks.sql

CREATE TABLE IF NOT EXISTS junior_tasks (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL,
  title        TEXT NOT NULL,
  detail       TEXT NOT NULL DEFAULT '',
  payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
  status       TEXT NOT NULL DEFAULT 'open',
  claim_id     TEXT,
  claimed_by   TEXT,
  lease_until  TIMESTAMPTZ,
  attempt      INTEGER NOT NULL DEFAULT 0,
  result       JSONB,
  error        TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT junior_tasks_status_check CHECK (status IN ('open','claimed','done','failed'))
);

CREATE INDEX IF NOT EXISTS junior_tasks_user_status_idx
  ON junior_tasks (user_id, status);
CREATE INDEX IF NOT EXISTS junior_tasks_user_created_idx
  ON junior_tasks (user_id, created_at);
