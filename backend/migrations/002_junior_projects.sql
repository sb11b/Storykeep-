-- Junior project registry + agent-run log (shared memory follow-up).
-- Reuses StoryKeep users. Apply after 001_junior_memory.sql.
--   psql "$DATABASE_URL" -f backend/migrations/002_junior_projects.sql

CREATE TABLE IF NOT EXISTS junior_projects (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  slug            TEXT NOT NULL,
  display_name    TEXT NOT NULL,
  kind            TEXT NOT NULL DEFAULT 'other'
                  CHECK (kind IN ('app','api','overlay','infra','other')),
  repo_url        TEXT,
  default_branch  TEXT NOT NULL DEFAULT 'main',
  notes           TEXT,
  meta            JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, slug)
);

CREATE INDEX IF NOT EXISTS junior_projects_user_slug_idx
  ON junior_projects (user_id, slug);

CREATE TABLE IF NOT EXISTS junior_agent_runs (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  project_slug     TEXT NOT NULL,
  prompt           TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'context_ready',
  cursor_agent_id  TEXT,
  thread_id        UUID REFERENCES junior_threads(id) ON DELETE SET NULL,
  meta             JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS junior_agent_runs_user_created_idx
  ON junior_agent_runs (user_id, created_at DESC);
