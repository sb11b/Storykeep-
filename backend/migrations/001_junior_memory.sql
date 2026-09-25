-- Junior shared chat memory — Railway Postgres
-- Source: design sketch (threads / messages / memories / sessions + FTS).
-- StoryKeep already has `users` (email, password_hash, display_name, …).
-- Do not CREATE TABLE users here — a sketch-shaped users table would clash
-- with the live login schema. All new tables reference existing users(id).
--
-- Sketch names → this repo (avoid colliding with junior_memory / grok_messages):
--   threads  → junior_threads
--   messages → junior_thread_messages
--   memories → junior_memories
--   sessions → junior_sessions
--
-- Apply:
--   psql "$DATABASE_URL" -f backend/migrations/001_junior_memory.sql
-- Also applied on API boot from `_create_schema`.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS junior_threads (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title         TEXT,
  venue_last    TEXT NOT NULL DEFAULT 'storykeep'
                CHECK (venue_last IN ('storykeep','phone','windows','voice')),
  status        TEXT NOT NULL DEFAULT 'open'
                CHECK (status IN ('open','archived')),
  summary       TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS junior_threads_user_updated_idx
  ON junior_threads (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS junior_thread_messages (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_id     UUID NOT NULL REFERENCES junior_threads(id) ON DELETE CASCADE,
  role          TEXT NOT NULL CHECK (role IN ('user','junior','system')),
  content       TEXT NOT NULL,
  venue         TEXT NOT NULL
                CHECK (venue IN ('storykeep','phone','windows','voice')),
  meta          JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS junior_thread_messages_thread_created_idx
  ON junior_thread_messages (thread_id, created_at ASC);

ALTER TABLE junior_thread_messages
  ADD COLUMN IF NOT EXISTS content_tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;

CREATE INDEX IF NOT EXISTS junior_thread_messages_fts_idx
  ON junior_thread_messages USING GIN (content_tsv);

ALTER TABLE junior_threads
  ADD COLUMN IF NOT EXISTS title_tsv tsvector
  GENERATED ALWAYS AS (
    to_tsvector('english', coalesce(title,'') || ' ' || coalesce(summary,''))
  ) STORED;

CREATE INDEX IF NOT EXISTS junior_threads_fts_idx ON junior_threads USING GIN (title_tsv);

-- Distinct from `junior_memory` (one standing markdown note per user).
CREATE TABLE IF NOT EXISTS junior_memories (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL DEFAULT 'note'
                CHECK (kind IN ('profile','preference','decision','note')),
  content       TEXT NOT NULL,
  source_thread UUID REFERENCES junior_threads(id) ON DELETE SET NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS junior_memories_user_idx ON junior_memories (user_id, kind);

CREATE TABLE IF NOT EXISTS junior_sessions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  venue         TEXT NOT NULL
                CHECK (venue IN ('storykeep','phone','windows','voice')),
  device_label  TEXT,
  last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS junior_sessions_user_venue_idx
  ON junior_sessions (user_id, venue, last_seen_at DESC);
