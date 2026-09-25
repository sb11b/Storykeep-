# Storykeep

A personal RSS reader and lifelong article archive. Subscribe to feeds, store the full text of stories (not just links), search across years of reading, tag and annotate what you keep, and export backups so the collection survives a dead laptop.

This is the Phase 1–2 slice: FastAPI + PostgreSQL backend and a web library you can use every day. The API already includes delta-sync endpoints for a later Android client.

## What you can do

- Add RSS/Atom feeds, grouped into categories
- Optional one-way import of Steve's Surface Vault (zip). Obsidian is paused; StoryKeep is the working archive. StoryKeep never writes to that folder on disk.
- One Notes workspace with destination + folder dropdowns: Vault, Additions, Books, Notes, Schoolwork. Edits update the StoryKeep DB row only. StoryKeep-authored notes keep the last 20 saves (or 30 days); **Undo last save** and History restore a prior version. A save that is under 20% of the stored length asks before overwrite. Vault originals stay read-only. **Work in Junior** loads the note on the server (80k cap, next chunk / heading if longer); the textarea is instructions only. **Apply to note** writes a revision, not a blind overwrite.
- Highlight and add overlay notes (with in-note highlights and images). Optional **Obsidian overlay pack** download — not required for backup.
- Read extracted article text in a dedicated reader, or listen with xAI speech (L from the start, Shift+L from a selected word; long books warn before synth)
- Save stories for later / for life, star them, mark read
- Tag articles and write notes
- Snapshot HTML so a dead original URL still has a copy; **PDF snapshot** keeps a printable copy on the `/app/var` volume
- Full-text search across titles, authors, summaries, and stored bodies
- **Primary backup:** dated Export JSON bundle (`archive.json` + note media in one zip) or database dump; uploaded to Backblaze B2 when configured
- **Junior memory:** one owner note (Junior full screen → Memory). Attached as a short system section on Junior requests (first 8k). Demo never sees or edits it. Do not dump it into reply footers.
- **Junior shared chat memory:** Railway Postgres tables (`junior_threads`, `junior_thread_messages`, `junior_memories`, `junior_sessions`, `junior_projects`, `junior_agent_runs`) plus `/api/v1/junior/threads|search|memories|projects|agent-context|agents` so StoryKeep, the phone app (`venue=phone`), and the Windows overlay share one history and can hand Cursor agents a project + memory pack. Distinct from the standing Memory note.
- **Junior live search:** owner chat can call `web_search` in the same thread (xAI live search). Current events, prices, docs, and “look this up” get cited public URLs. Demo has no search tool. Missing key → “Search unavailable, retry later.”
- **Thin export** from a Junior reply: Word (`.docx`), Markdown, and `.txt`. Code fences keep Copy.
- **Calendar:** Fastmail CalDAV (per-user app password or API token, encrypted on the server). Library **Calendar** is week/month. Junior proposes an event; Confirm writes it.
- **Mail:** Fastmail JMAP (Railway `FASTMAIL_TOKEN`, or an owner-only encrypted token). Library **Mail** lists Inbox / Sent / Drafts (50 per page). Compose asks Confirm before Send. Demo has no mail. Junior “summarize unread” uses that same list (grok-4.6 · low) and never sends without Confirm.

## Stack

| Layer | Choice |
| --- | --- |
| API | Python, FastAPI, SQLAlchemy |
| Database | PostgreSQL 16 with `tsvector` search |
| Extraction | Trafilatura, with Readability as fallback |
| Web | Next.js, Tailwind, shadcn/ui |
| Backup | Local files; Amazon S3 if `S3_BUCKET` is set |

Planning documents live in `docs/`:

- `docs/rss_reader_schema.sql` — 11-table schema
- `docs/rss_reader_api_design.md` — endpoint contract
- `docs/rss_reader_architecture.md` — why these decisions

**Windows, no Ubuntu:** follow [`docs/START_HERE.md`](docs/START_HERE.md) — open the repo in Cursor, push to GitHub, deploy on Railway. You do not need WSL or Docker on the PC.

## Local setup

PostgreSQL 16, Python 3.12, and Node 22.

```bash
# database
createdb storykeep   # or use the docker-compose db service

# api
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://storykeep:storykeep@127.0.0.1:5432/storykeep
uvicorn app.main:app --reload --host 0.0.0.0 --port 18741

# web (second terminal)
cd frontend
npm install
API_ORIGIN=http://127.0.0.1:18741 npm run dev -- --port 43123
```

Open [http://127.0.0.1:43123](http://127.0.0.1:43123). The published demo login is closed. Sign in with your own account.

Steve: use Railway (`railway up --service storykeep`) after `NEXT_OUTPUT=export npm --prefix frontend run build`. Hard-refresh the browser. Do not run local Docker, WSL, or Ubuntu for this project.

## Environment

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Postgres URL. Parsed into host/user/password. Public Railway hosts use TLS without verifying the proxy cert. Do not set `NODE_TLS_REJECT_UNAUTHORIZED=0`. |
| `SECRET_KEY` | JWT signing key |
| `SEED_DEMO` | Local only. May lock a legacy demo row; never creates a login. Off in production. |
| `S3_BUCKET` | Optional backup destination |
| `BACKUP_INTERVAL_HOURS` | Scheduled S3/B2 database dump interval (default 24; `0` disables) |
| `S3_PREFIX` | Object prefix, default `storykeep` |
| `API_ORIGIN` | Next.js rewrite target for the API |
| `XAI_API_KEY` | xAI key from [console.x.ai](https://console.x.ai) (starts with `xai-`). Enables Listen, dictation, and the Junior chat bubble. Server only — never in git or the browser. |
| `XAI_CHAT_MODEL` | Chat model, default `grok-4.6`. Auto uses grok-4.6 with reasoning `low` (short) or `xhigh` (school/code). |
| `JUNIOR_CRON_SECRET` | Shared secret for `POST /api/v1/junior/jobs/run` (Railway cron). StoryKeep also ticks due jobs every minute. |
| `FASTMAIL_CALDAV_URL` | Optional. Fastmail CalDAV origin; default `https://caldav.fastmail.com`. Connect still shows if this is unset. |
| `FASTMAIL_TOKEN` | Fastmail JMAP API token for owner Mail. Server only — never in the browser or logs. |
| `RAILWAY_API_TOKEN` | Railway account/project token for Junior deploy status + deploy triggers. Server only. |
| `GITHUB_TOKEN` | GitHub fine-grained PAT for Junior repo status (commits, PRs, CI). Server only. |
| `GITHUB_REPO` | Repo slug for Junior GitHub tools, default `sb11b/Storykeep-`. |

The Junior bubble is a movable panel. Replies stay in the session until **Add to notes**, which creates or updates a StoryKeep addition (`guid storykeep-note:` / `StoryKeep/Additions/`). It never overwrites `Steve's Surface Vault/**`. Chat is capped at 120 requests per hour per user (`CHAT_REQUESTS_PER_HOUR`). **Image** (next to the paperclip) generates a picture from the typed prompt via the xAI image API (`XAI_API_KEY` on the server only), stores it as owner-only media, and keeps it in the thread. Image gen is 10 per hour (`IMAGINE_REQUESTS_PER_HOUR`). Demo accounts cannot use chat or Imagine. Dictation uses streaming STT at `$0.20/hr` via the server.

## Junior shared chat memory

Durable history for StoryKeep, the phone app, and the Windows overlay lives in **Railway Postgres** — not in xAI. Design sketch: [`docs/junior_shared_memory.md`](docs/junior_shared_memory.md). `XAI_API_KEY` is inference only. User turns are always saved; a Junior reply is generated with last N messages + `summary` + facts when the key is set (`reply_status=ok`). Missing key → `stubbed_no_key`. xAI errors do not roll back the user row (`xai_error`).

**Env:** same `DATABASE_URL` as the rest of StoryKeep (Railway: `DATABASE_URL=${{Postgres.DATABASE_URL}}`). Same `SECRET_KEY` / session cookie (`sk_access`) or `Authorization: Bearer` JWT. Every query is scoped to the signed-in user (`require_user`). Closed demo accounts get 401/403. Do not put DB or xAI secrets in git.

**Tables** (reuses existing `users`; does not create a second user store):

| Table | Role |
| --- | --- |
| `junior_threads` | One conversation + FTS on title/summary |
| `junior_thread_messages` | Turns (`user` / `junior` / `system`) + FTS on content |
| `junior_memories` | Durable facts (`profile` / `preference` / `decision` / `note`) |
| `junior_sessions` | Last-seen venue/device |
| `junior_projects` | Repo/app registry (slug unique per user) |
| `junior_agent_runs` | Cursor-agent launch attempts (`context_ready` stub) |

`junior_memory` (singular) remains the one standing markdown note at `GET/PUT /api/v1/junior/memory`.

**Apply the migration**

1. Automatic: API boot runs `001_junior_memory.sql` then `002_junior_projects.sql` from `_create_schema`. The container includes `backend/migrations` at `/app/migrations`.
2. Manual on Railway Postgres (psql against the plugin URL — never commit that URL):

```bash
psql "$DATABASE_URL" -f backend/migrations/001_junior_memory.sql
psql "$DATABASE_URL" -f backend/migrations/002_junior_projects.sql
```

Owner boot seed (`angry.tune8751@fastmail.com`): projects `storykeep`, `junior-phone` (Junior mobile — [origin repo](https://cursor.com/codebase/steve-bitsko/junior-mobile)), `windows-overlay`, plus decision memories (Postgres is source of truth; xAI is inference; three venues; Cursor agents use a context pack).

**Endpoints** (cookie or Bearer; prefix `/api/v1`)

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/junior/threads` | List recent threads for the signed-in user |
| `POST` | `/api/v1/junior/threads` | Start a thread (`title`, `venue`). Optional `text` is the first turn. |
| `GET` | `/api/v1/junior/threads/{id}/messages` | Full history |
| `POST` | `/api/v1/junior/threads/{id}/messages` | Send a turn (`text` or `content`, `venue`, optional `meta`) |
| `GET` | `/api/v1/junior/messages` | Same history; omit `thread_id` to read the last `open` thread |
| `POST` | `/api/v1/junior/messages` | Same turn; omit `thread_id` to use last `open` thread (or create one) |
| `POST` | `/api/v1/junior/threads/{id}/continue` | Resume a thread; with `text` this is another turn |
| `GET` | `/api/v1/junior/search?q=` | FTS over that user’s threads/messages |
| `GET` | `/api/v1/junior/memories` | Durable facts (`?kind=` optional) |
| `POST` | `/api/v1/junior/memories` | Add a fact, or update when `id` is set |
| `GET` | `/api/v1/junior/projects` | List project registry |
| `GET` | `/api/v1/junior/projects/{slug}` | One project |
| `POST` | `/api/v1/junior/projects` | Upsert by slug |
| `GET` | `/api/v1/junior/agent-context?project=&q=` | Pack for a Cursor agent (project + thread + memories + search) |
| `POST` | `/api/v1/junior/agents` | Record a launch (`context_ready`); does not call Cursor |

Venues: `storykeep`, `phone`, `windows`, `voice`. **Phone is first-class** (`venue=phone` on the same routes — no separate phone DB). Overlay uses `venue=windows`. Message `meta` can hold overlay screen/OCR or voice extras (`screen`, `voice`, `dictation_target`). See [`docs/junior_shared_memory.md`](docs/junior_shared_memory.md).

S3 is optional. Without credentials, backups stay in `backend/var/backups/`.

## Android (Talk / Type shell)

The Talk / Type shell lives in [`android/`](android/README.md): Kotlin, Jetpack Compose, min SDK 26. Three screens (Home, Conversation, Stories) with local stub Talk / Type / Save. Talk session core kills voice on Type, End, leave, lock, and network loss. No Grok Voice APIs. Open the `android` folder in Android Studio to run it.

Railway still deploys the web app from the root `Dockerfile`. The Android module is not in that image.

`POST /api/v1/sync/delta` and `POST /api/v1/sync/push` remain the later offline-reader contract. Saved articles include `content_html` so a phone can keep the text without hitting the original site.

## Security (Junior lockdown)

- Junior API routes require an authenticated owner session (`require_user`). Unauthenticated requests get 401; closed demo accounts get 401/403. No public Junior surface.
- Session cookie `sk_access`: HttpOnly, Secure in production, SameSite=Lax.
- Production trusts Railway `X-Forwarded-Proto` and redirects HTTP to HTTPS (`/health` stays plain HTTP for probes).
- Application logs never include request bodies, chat text, `Authorization`, or cookies — only ids, status, latency, and char counts.
- **Postgres:** use Railway private networking (`*.railway.internal`) when possible; grant the app a non-superuser DB role; encrypt database dumps at rest with a key stored separately from the dump file (e.g. B2 credentials in Railway vars, not beside the `.sql` on disk).

## Deploy on Railway

One service plus Railway PostgreSQL. The image serves the API and the web UI on a single public URL.

1. New Railway project → deploy this repo (GitHub) or `npx @railway/cli up`
2. Add a **PostgreSQL** plugin
3. On the web service, set `DATABASE_URL=${{Postgres.DATABASE_URL}}`
4. Generate a public domain

Demo login after first boot is closed. Use your own account (`angry.tune8751@fastmail.com` on production).

Step-by-step notes, optional `SECRET_KEY`, and backup caveats: [`docs/railway.md`](docs/railway.md).

Lightsail / Docker Compose still works for a VPS if you prefer that over Railway.
