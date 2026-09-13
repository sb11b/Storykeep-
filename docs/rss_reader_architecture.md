# Storykeep Architecture

Personal RSS reader and long-term article archive. This document is the implementation map for Phase 1 (backend) and Phase 2 (web). Android (Phase 4) consumes the same API.

## Why these choices

| Decision | Why |
| --- | --- |
| PostgreSQL | Native full-text search (`tsvector` / `ts_rank_cd`), JSONB preferences, durable single-node store that fits a $5 Lightsail instance. |
| Full article text in `articles` | Links die. The archive is the product. Search ranks title, then summary, then body. |
| Separate `archives` table | A readability/HTML snapshot is a second copy of the page as fetched, independent of the cleaned reading view. |
| `change_log` + `sync_devices` | Android should not re-download the whole archive. Delta sync is a first-class API, not a later retrofit. |
| FastAPI | Typed request/response models that match the API design 1:1; easy background tasks for fetch + extract. |
| Trafilatura over Newspaper3k | More reliable extraction across news, blogs, and government sites; Newspaper3k is heavier and often breaks on current Python. |
| JWT + cookie | Bearer token for Android; httpOnly cookie for the web client via the Next.js rewrite proxy. |
| S3 optional | Local `pg_dump` / JSON export always works. S3 is a redundancy target, not a runtime dependency. |

## Repository layout

```
backend/                 FastAPI app
  app/
    main.py              lifespan, CORS, routers, scheduler
    config.py
    database.py
    models.py
    schemas.py
    auth.py
    deps.py
    routers/
    services/            rss, extractor, backup, archive, changelog
  requirements.txt
frontend/                Next.js + Tailwind + shadcn/ui
docs/                    schema + API + this file
docker-compose.yml       Postgres + API + web for Lightsail
```

## Data flow

1. User adds a feed URL.
2. `services.rss` fetches and parses with `feedparser` (honors ETag / Last-Modified).
3. New items are upserted on `(feed_id, guid)`.
4. For each new item, `services.extractor` downloads the article URL and stores cleaned HTML + plain text.
5. Generated `search_vector` updates automatically.
6. Saving an article (`is_saved=true`) writes an `archives` row so the page survives even if the source later 404s.
7. Mutations append `change_log` rows for `/sync/delta`.

## Background work

A process-local scheduler refreshes due feeds (`last_fetched_at` older than `fetch_interval_minutes`). On a single Lightsail box this is enough. If the API is scaled later, move refresh to a worker.

## Backup strategy (from day one)

- `POST /backups` with `backup_type=db_dump` runs `pg_dump` to `backend/var/backups/`.
- `backup_type=export_json` writes a user-scoped archive (feeds, saved articles, tags, notes).
- If `S3_BUCKET` is set, the file is also uploaded. If not, destination falls back to `local`.
- Restore: `psql storykeep < dump.sql` or re-import the JSON export. Article snapshots restore from **Restore…** in the reader (`POST /articles/{id}/restore`).

## Auth

Passwords hashed with bcrypt. Access tokens last 14 days (personal instance; refresh tokens can be added when Android ships offline login).

## Hosting (Lightsail)

`docker compose up -d` publishes the web UI (port 80 → Next) and keeps Postgres on the private network. Point a domain at the instance if you buy one. Monthly cost stays in the $5–10 Lightsail band plus optional S3.

## Phase boundaries

- **Shipped now:** schema, API, web reader, search, tags, notes, save/archive, local backup/export, delta sync endpoint.
- **Phase 3 shipped:** scheduled S3/B2 database dumps (`BACKUP_INTERVAL_HOURS`, default 24); PDF snapshots (`POST /articles/{id}/archive` `{ "type": "pdf" }`); one-click restore UI (`GET /articles/{id}/archives`, `POST /articles/{id}/restore`).
- **Phase 4:** Android client using `/sync/delta` + offline `content_html`.
- **Phase 5:** extraction quality pass, integrity checks, unread-performance indexes under large archives.

## Local run

See the root `README.md`. Default demo account is created on first boot when `SEED_DEMO=1`.
