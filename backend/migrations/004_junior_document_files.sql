-- Junior document files — binary attachments stored on disk, referenced by document slug.
-- Reuses StoryKeep users. Apply after 003_junior_documents.sql.
--   psql "$DATABASE_URL" -f backend/migrations/004_junior_document_files.sql

CREATE TABLE IF NOT EXISTS junior_document_files (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  document_slug TEXT NOT NULL,
  filename      TEXT NOT NULL,
  content_type  TEXT NOT NULL DEFAULT 'application/octet-stream',
  byte_size     INTEGER,
  storage_path  TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS junior_document_files_user_slug_idx
  ON junior_document_files (user_id, document_slug);
