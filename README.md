# Storykeep

A personal RSS reader and lifelong article archive. Subscribe to feeds, store the full text of stories (not just links), search across years of reading, tag and annotate what you keep, and export backups so the collection survives a dead laptop.

This is the Phase 1–2 slice: FastAPI + PostgreSQL backend and a web library you can use every day. The API already includes delta-sync endpoints for a later Android client.

## What you can do

- Add RSS/Atom feeds, grouped into categories
- Import Steve's Surface Vault (zip). Original markdown stays in Obsidian.
- Highlight, add overlay notes (with in-note highlights and images), and save corrections, then **Download Obsidian pack**
- Read extracted article text in a dedicated reader, or listen with xAI speech (L from the start, Shift+L from a selected word; long books warn before synth)
- Save stories for later / for life, star them, mark read
- Tag articles and write notes
- Snapshot HTML so a dead original URL still has a copy
- Full-text search across titles, authors, summaries, and stored bodies
- Export JSON or dump the database; optional S3 upload when configured

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

Open [http://127.0.0.1:43123](http://127.0.0.1:43123). A demo account is created on first boot:

- email: `steve@storykeep.local`
- password: `commonplace`

Steve: use Railway (`railway up --service storykeep`) after `NEXT_OUTPUT=export npm --prefix frontend run build`. Hard-refresh the browser. Do not run local Docker, WSL, or Ubuntu for this project.

## Environment

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy URL |
| `SECRET_KEY` | JWT signing key |
| `SEED_DEMO` | Create the demo user and sample feeds (`1` by default) |
| `S3_BUCKET` | Optional backup destination |
| `S3_PREFIX` | Object prefix, default `storykeep` |
| `API_ORIGIN` | Next.js rewrite target for the API |
| `XAI_API_KEY` | xAI key from [console.x.ai](https://console.x.ai) (starts with `xai-`). Enables Listen and the Grok chat bubble. Server only — never in git or the browser. |
| `XAI_CHAT_MODEL` | Optional chat model, default `grok-4` |

The Grok bubble is a movable panel. Replies stay in the session until **Add to notes**, which creates or updates a StoryKeep addition (`guid storykeep-note:` / `StoryKeep/Additions/`). It never overwrites `Steve's Surface Vault/**`. Chat is capped at 30 requests per hour per user.

S3 is optional. Without credentials, backups stay in `backend/var/backups/`.

## Android later

`POST /api/v1/sync/delta` and `POST /api/v1/sync/push` are the contract for an offline reader. Saved articles include `content_html` so a phone can keep the text without hitting the original site.

## Deploy on Railway

One service plus Railway PostgreSQL. The image serves the API and the web UI on a single public URL.

1. New Railway project → deploy this repo (GitHub) or `npx @railway/cli up`
2. Add a **PostgreSQL** plugin
3. On the web service, set `DATABASE_URL=${{Postgres.DATABASE_URL}}`
4. Generate a public domain

Demo login after first boot: `steve@storykeep.local` / `commonplace`

Step-by-step notes, optional `SECRET_KEY`, and backup caveats: [`docs/railway.md`](docs/railway.md).

Lightsail / Docker Compose still works for a VPS if you prefer that over Railway.
