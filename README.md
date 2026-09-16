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
| `SEED_DEMO` | Create the demo user and sample feeds (`1` by default) |
| `S3_BUCKET` | Optional backup destination |
| `BACKUP_INTERVAL_HOURS` | Scheduled S3/B2 database dump interval (default 24; `0` disables) |
| `S3_PREFIX` | Object prefix, default `storykeep` |
| `API_ORIGIN` | Next.js rewrite target for the API |
| `XAI_API_KEY` | xAI key from [console.x.ai](https://console.x.ai) (starts with `xai-`). Enables Listen, dictation, and the Junior chat bubble. Server only — never in git or the browser. |
| `XAI_CHAT_MODEL` | Chat model, default `grok-4.6`. Auto uses grok-4.6 with reasoning `low` (short) or `xhigh` (school/code). |
| `JUNIOR_CRON_SECRET` | Shared secret for `POST /api/v1/junior/jobs/run` (Railway cron). StoryKeep also ticks due jobs every minute. |
| `FASTMAIL_CALDAV_URL` | Optional. Fastmail CalDAV origin; default `https://caldav.fastmail.com`. Connect still shows if this is unset. |
| `FASTMAIL_TOKEN` | Fastmail JMAP API token for owner Mail. Server only — never in the browser or logs. |

The Junior bubble is a movable panel. Replies stay in the session until **Add to notes**, which creates or updates a StoryKeep addition (`guid storykeep-note:` / `StoryKeep/Additions/`). It never overwrites `Steve's Surface Vault/**`. Chat is capped at 120 requests per hour per user (`CHAT_REQUESTS_PER_HOUR`). **Image** (next to the paperclip) generates a picture from the typed prompt via the xAI image API (`XAI_API_KEY` on the server only), stores it as owner-only media, and keeps it in the thread. Image gen is 10 per hour (`IMAGINE_REQUESTS_PER_HOUR`). Demo accounts cannot use chat or Imagine. Dictation uses streaming STT at `$0.20/hr` via the server.

S3 is optional. Without credentials, backups stay in `backend/var/backups/`.

## Android later

`POST /api/v1/sync/delta` and `POST /api/v1/sync/push` are the contract for an offline reader. Saved articles include `content_html` so a phone can keep the text without hitting the original site.

## Deploy on Railway

One service plus Railway PostgreSQL. The image serves the API and the web UI on a single public URL.

1. New Railway project → deploy this repo (GitHub) or `npx @railway/cli up`
2. Add a **PostgreSQL** plugin
3. On the web service, set `DATABASE_URL=${{Postgres.DATABASE_URL}}`
4. Generate a public domain

Demo login after first boot is closed. Use your own account (`stevebitsko@duck.com` on production).

Step-by-step notes, optional `SECRET_KEY`, and backup caveats: [`docs/railway.md`](docs/railway.md).

Lightsail / Docker Compose still works for a VPS if you prefer that over Railway.
