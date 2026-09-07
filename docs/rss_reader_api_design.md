# Storykeep API Design

Base URL: `/api/v1`  
Auth: JWT access token in `Authorization: Bearer <token>` or `sk_access` httpOnly cookie.  
Content type: `application/json` unless noted.

All timestamps are ISO-8601 UTC. IDs are UUIDs.

## Conventions

### Pagination

```
GET ...?limit=50&offset=0
```

Response envelope for lists:

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

### Errors

```json
{
  "detail": "Feed URL could not be parsed",
  "code": "feed_parse_failed"
}
```

| Status | Meaning |
| --- | --- |
| 400 | Validation / parse failure |
| 401 | Missing or expired token |
| 403 | Authenticated but not allowed |
| 404 | Resource not found (or not owned) |
| 409 | Unique constraint (duplicate feed, email) |
| 429 | Rate limited |
| 502 | Upstream fetch failed |

Rate limit (personal instance): 120 requests / minute / user. Feed refresh is limited to 1 concurrent refresh per feed.

---

## 1. Authentication

### `POST /auth/register`

```json
{ "email": "steve@example.com", "password": "••••••••", "display_name": "Steve" }
```

Returns `{ "user": User, "access_token": "...", "token_type": "bearer" }` and sets cookie.

### `POST /auth/login`

```json
{ "email": "steve@example.com", "password": "••••••••" }
```

Same response as register.

### `POST /auth/logout`

Clears cookie. `{ "ok": true }`

### `GET /auth/me`

Returns `User`.

**User**

```json
{
  "id": "…",
  "email": "steve@example.com",
  "display_name": "Steve",
  "preferences": { "theme": "paper", "items_per_page": 40 },
  "created_at": "2026-09-07T00:00:00Z"
}
```

---

## 2. Categories

### `GET /categories`
### `POST /categories` `{ "name": "Science", "color": "#3d6b4f", "sort_order": 1 }`
### `PATCH /categories/{id}`
### `DELETE /categories/{id}`  — feeds in the category are uncategorized, not deleted

---

## 3. Feeds

### `GET /feeds`

Query: `category_id`, `active=true|false`

Each feed includes `unread_count`, `saved_count`, `article_count`.

### `POST /feeds`

```json
{ "url": "https://hnrss.org/frontpage", "category_id": null }
```

Server fetches the feed, stores metadata, and imports recent items (default 50). Extraction of full article text runs asynchronously after insert.

### `GET /feeds/{id}`
### `PATCH /feeds/{id}` `{ "title", "category_id", "is_active", "fetch_interval_minutes" }`
### `DELETE /feeds/{id}`  — cascades articles unless they are saved; saved articles are detached to a “Kept” tombstone? **Decision:** cascade delete unpublished/unread only is complex. MVP: cascade all; client warns if saved articles exist (`?force=true` required when saved_count > 0).

### `POST /feeds/{id}/refresh`
### `POST /feeds/refresh`  — refresh all active feeds for the user

**Feed**

```json
{
  "id": "…",
  "url": "https://hnrss.org/frontpage",
  "title": "Hacker News",
  "description": "…",
  "site_url": "https://news.ycombinator.com",
  "favicon_url": null,
  "category_id": null,
  "last_fetched_at": "2026-09-07T02:00:00Z",
  "last_error": null,
  "is_active": true,
  "unread_count": 12,
  "saved_count": 3,
  "article_count": 40
}
```

---

## 4. Articles

### `GET /articles`

Query:

| Param | Values |
| --- | --- |
| `feed_id` | UUID |
| `category_id` | UUID |
| `tag_id` | UUID |
| `saved` | true/false |
| `starred` | true/false |
| `read` | true/false |
| `q` | full-text query (same engine as `/search`) |
| `since` | ISO timestamp |
| `limit`, `offset` |
| `sort` | `published_desc` (default), `published_asc`, `saved_desc` |

### `GET /articles/{id}`  — includes tags, annotations, latest archive

### `PATCH /articles/{id}`

```json
{ "is_read": true, "is_saved": true, "is_starred": false }
```

Setting `is_saved=true` stamps `saved_at` and triggers a readability archive if none exists.

### `POST /articles/{id}/extract`  — re-fetch original URL and replace stored text/html

### `POST /articles/mark-read`

```json
{ "ids": ["…"], "is_read": true }
```

---

## 5. Tags

### `GET /tags`  — includes `article_count`
### `POST /tags` `{ "name": "to-reread", "color": "#c45c26" }`
### `PATCH /tags/{id}`
### `DELETE /tags/{id}`

### `PUT /articles/{id}/tags` `{ "tag_ids": ["…"] }`  — replace set
### `POST /articles/{id}/tags` `{ "name": "to-reread" }`  — create-or-attach

---

## 6. Annotations (notes)

### `GET /articles/{id}/annotations`
### `POST /articles/{id}/annotations` `{ "body": "…", "quote": "optional highlight" }`
### `PATCH /annotations/{id}`
### `DELETE /annotations/{id}`
### `GET /annotations`  — all notes for the user, newest first

---

## 7. Search

### `GET /search?q=fusion+reactor&saved=true&limit=25`

Uses PostgreSQL `tsvector` / `ts_rank_cd`. Title matches rank highest, then author/summary, then body.

```json
{
  "items": [
    {
      "article": { "id": "…", "title": "…", "feed_title": "NASA" },
      "rank": 0.82,
      "headline": "…<b>fusion</b>…"
    }
  ],
  "total": 4
}
```

Empty `q` returns 400.

---

## 8. Archives (link-rot fallback)

### `POST /articles/{id}/archive` `{ "type": "html" }`
### `GET /articles/{id}/archives`
### `GET /archives/{id}`  — returns stored HTML or a download URL

`type=pdf` is reserved; MVP stores cleaned HTML (`readability`).

---

## 8b. Speech (xAI TTS)

### `GET /tts`

Returns `{ "enabled": true, "provider": "xai", "voices": [{ "voice_id": "eve", "name": "Eve" }] }`. Requires auth. `enabled` is false until `XAI_API_KEY` is set.

### `GET /articles/{id}/tts?voice_id=eve&chunk=0`

Returns `audio/mpeg` for one chunk of the stored article text (title, byline, body). Headers: `X-TTS-Chunk`, `X-TTS-Chunks`. Chunks are split under the xAI 15,000-character limit. 401/503 if the key is missing or rejected.

---

## 9. Sync (web + Android)

### `POST /sync/delta`

```json
{
  "device_id": "pixel-8",
  "device_name": "Pixel 8",
  "cursor": 0,
  "limit": 200
}
```

```json
{
  "cursor": 1842,
  "has_more": false,
  "changes": [
    { "entity_type": "article", "entity_id": "…", "action": "upsert", "payload": { } }
  ]
}
```

Clients persist `cursor` and send it on the next call. Designed so an Android offline reader can pull only what changed.

### `POST /sync/push`

```json
{
  "device_id": "pixel-8",
  "mutations": [
    { "entity_type": "article", "entity_id": "…", "action": "upsert", "payload": { "is_read": true } }
  ]
}
```

Accepted article mutations: `is_read`, `is_saved`, `is_starred`. Last-write-wins on `updated_at`.

---

## 10. Backups & export

### `POST /backups`

```json
{ "backup_type": "export_json", "destination": "local" }
```

`destination=s3` uses `S3_BUCKET` when configured; otherwise the request is stored locally and `destination` is recorded as `local` with a warning.

### `GET /backups`
### `GET /backups/{id}/download`  — file stream

### `GET /export`  — convenience alias: immediate JSON export of the current user's archive (feeds, saved articles, tags, notes)

---

## 11. Preferences

### `GET /preferences`
### `PUT /preferences`

```json
{ "theme": "paper", "items_per_page": 40, "mark_read_on_open": true }
```

Stored in `users.preferences` JSONB.

---

## Dashboard extras

### `GET /stats`

```json
{
  "feed_count": 6,
  "article_count": 842,
  "unread_count": 37,
  "saved_count": 128,
  "annotation_count": 19,
  "oldest_saved_at": "2026-01-03T00:00:00Z"
}
```

---

## Mobile-specific notes

- Prefer `/sync/delta` over paging `/articles` on every launch.
- `/articles?saved=true` is the offline reading set; Android should persist `content_html`.
- Images are not proxied in MVP; clients load `image_url` directly.
- Push notifications (Phase 4) will be `POST /devices/{id}/push-token` — not implemented yet.
