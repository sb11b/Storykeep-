-- Storykeep — PostgreSQL schema
-- Personal RSS reader and lifelong article archive
-- 11 tables: users, categories, feeds, articles, tags, article_tags,
-- annotations, archives, backups, sync_devices, change_log

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------------------
-- 1. users
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    preferences JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 2. categories  (user-defined feed folders)
-- ---------------------------------------------------------------------------
CREATE TABLE categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    color TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, name)
);

CREATE INDEX categories_user_idx ON categories (user_id, sort_order);

-- ---------------------------------------------------------------------------
-- 3. feeds
-- ---------------------------------------------------------------------------
CREATE TABLE feeds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    category_id UUID REFERENCES categories (id) ON DELETE SET NULL,
    url TEXT NOT NULL,
    title TEXT,
    description TEXT,
    site_url TEXT,
    favicon_url TEXT,
    etag TEXT,
    last_modified TEXT,
    last_fetched_at TIMESTAMPTZ,
    last_error TEXT,
    fetch_interval_minutes INTEGER NOT NULL DEFAULT 60,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, url)
);

CREATE INDEX feeds_user_active_idx ON feeds (user_id, is_active);
CREATE INDEX feeds_category_idx ON feeds (category_id);

-- ---------------------------------------------------------------------------
-- 4. articles  (full text stored, not just links)
-- ---------------------------------------------------------------------------
CREATE TABLE articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_id UUID NOT NULL REFERENCES feeds (id) ON DELETE CASCADE,
    guid TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    author TEXT,
    published_at TIMESTAMPTZ,
    summary TEXT,
    content_text TEXT,
    content_html TEXT,
    image_url TEXT,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    is_saved BOOLEAN NOT NULL DEFAULT FALSE,
    is_starred BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMPTZ,
    saved_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (feed_id, guid)
);

CREATE INDEX articles_feed_published_idx ON articles (feed_id, published_at DESC);
CREATE INDEX articles_saved_idx ON articles (feed_id, is_saved) WHERE is_saved;
CREATE INDEX articles_unread_idx ON articles (feed_id, is_read, published_at DESC);
CREATE INDEX articles_url_trgm_idx ON articles USING GIN (url gin_trgm_ops);
CREATE INDEX articles_title_trgm_idx ON articles USING GIN (title gin_trgm_ops);

ALTER TABLE articles
    ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(author, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(summary, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(content_text, '')), 'C')
    ) STORED;

CREATE INDEX articles_search_idx ON articles USING GIN (search_vector);

-- ---------------------------------------------------------------------------
-- 5. tags
-- ---------------------------------------------------------------------------
CREATE TABLE tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    color TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, lower(name))
);

CREATE INDEX tags_user_idx ON tags (user_id);

-- ---------------------------------------------------------------------------
-- 6. article_tags
-- ---------------------------------------------------------------------------
CREATE TABLE article_tags (
    article_id UUID NOT NULL REFERENCES articles (id) ON DELETE CASCADE,
    tag_id UUID NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (article_id, tag_id)
);

CREATE INDEX article_tags_tag_idx ON article_tags (tag_id);

-- ---------------------------------------------------------------------------
-- 7. annotations  (notes and optional quote highlights)
-- ---------------------------------------------------------------------------
CREATE TABLE annotations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    article_id UUID NOT NULL REFERENCES articles (id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    quote TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX annotations_article_idx ON annotations (article_id, created_at);
CREATE INDEX annotations_user_idx ON annotations (user_id, updated_at DESC);

-- ---------------------------------------------------------------------------
-- 8. archives  (HTML/PDF snapshot if the original link dies)
-- ---------------------------------------------------------------------------
CREATE TABLE archives (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID NOT NULL REFERENCES articles (id) ON DELETE CASCADE,
    archive_type TEXT NOT NULL CHECK (archive_type IN ('html', 'pdf', 'readability')),
    content TEXT,
    storage_backend TEXT NOT NULL DEFAULT 'db' CHECK (storage_backend IN ('db', 'local', 's3')),
    storage_path TEXT,
    checksum TEXT,
    byte_size INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX archives_article_idx ON archives (article_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- 9. backups  (local dumps + optional S3 copies)
-- ---------------------------------------------------------------------------
CREATE TABLE backups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users (id) ON DELETE SET NULL,
    backup_type TEXT NOT NULL CHECK (backup_type IN ('db_dump', 'export_json', 'export_html')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'success', 'failed')),
    destination TEXT NOT NULL CHECK (destination IN ('local', 's3')),
    location TEXT,
    size_bytes BIGINT,
    error TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX backups_started_idx ON backups (started_at DESC);

-- ---------------------------------------------------------------------------
-- 10. sync_devices  (delta sync for web + Android)
-- ---------------------------------------------------------------------------
CREATE TABLE sync_devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    device_id TEXT NOT NULL,
    device_name TEXT,
    last_sync_at TIMESTAMPTZ,
    cursor BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, device_id)
);

-- ---------------------------------------------------------------------------
-- 11. change_log  (monotonically increasing cursor for mobile delta sync)
-- ---------------------------------------------------------------------------
CREATE TABLE change_log (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('upsert', 'delete')),
    payload JSONB,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX change_log_user_cursor_idx ON change_log (user_id, id);

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER feeds_updated_at BEFORE UPDATE ON feeds
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER articles_updated_at BEFORE UPDATE ON articles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER annotations_updated_at BEFORE UPDATE ON annotations
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
