# Deploy Storykeep on Railway

One web service plus Railway PostgreSQL. The container serves the API and the web library on the same public URL.

## 1. Create the project

1. Open [Railway](https://railway.app) and start a new project.
2. **Deploy from GitHub**. Railway cannot see the Origin repo. Push `main` to GitHub first (`sb11b/Storykeep-` is empty until you do). See [`START_HERE.md`](START_HERE.md) step 5.
3. Railway picks up the root `Dockerfile` and `railway.toml`.

CLI alternative:

```bash
npx @railway/cli login
npx @railway/cli init
npx @railway/cli add --database postgres
npx @railway/cli up
npx @railway/cli domain
```

## 2. Add PostgreSQL

In the project: **New → Database → PostgreSQL**.

On the Storykeep service, add a variable that points at the database:

```
DATABASE_URL=${{Postgres.DATABASE_URL}}
```

Railway’s URL looks like `postgresql://…`. Storykeep parses **host, port, user, password, and database** from that URL and connects with those fields. It does **not** pass the raw string (or its `sslmode` / `sslrootcert` query) into the engine.

The public TCP proxy (`*.proxy.rlwy.net`) uses a cert that is not in the default CA store. Public hosts encrypt with `sslmode=require` (no CA verify). Local Postgres, Docker Compose `db`, and `*.railway.internal` stay unencrypted.

Do **not** set `NODE_TLS_REJECT_UNAUTHORIZED=0`. That Node flag disables TLS for the whole process and is a last-resort workaround only. The web UI never talks to Postgres; seed and the API use this engine config.

## 3. Variables

| Variable | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` | Yes | From the Postgres plugin |
| `SECRET_KEY` | Recommended | Any long random string. If you skip it, a stable key is derived from the database URL. |
| `SEED_DEMO` | No | Local/dev only. Off in production. Never creates a demo login; `steve@storykeep.local` stays closed. |
| `S3_BUCKET` | No | Optional AWS S3 bucket if you are not using Backblaze |
| `B2_KEY_ID` | No | Backblaze application key ID |
| `B2_APPLICATION_KEY` | No | Backblaze application key (never put this in git or the browser) |
| `B2_BUCKET` | No | Backblaze bucket name |
| `B2_ENDPOINT` | No | S3-compatible endpoint, e.g. `https://s3.us-west-004.backblazeb2.com` |
| `B2_REGION` | No | Backblaze region, e.g. `us-west-004` |
| `BACKUP_INTERVAL_HOURS` | No | Phase 3 scheduled S3/B2 `pg_dump`. Default 24. Set `0` to disable. |
| `XAI_API_KEY` | No | xAI API key (`xai-…`) for Listen, dictation, and the Grok chat bubble. Server only — never in the browser. |
| `XAI_TTS_URL` | No | xAI TTS endpoint. Default `https://api.x.ai/v1/tts`. |
| `XAI_TTS_VOICE` | No | Default Listen voice id when the browser has no saved pick. Example: `castor`. Default `eve`. |
| `XAI_CHAT_MODEL` | No | Chat model, default `grok-4` |
| `FASTMAIL_CALDAV_URL` | No | Optional CalDAV origin. Defaults to `https://caldav.fastmail.com`. Missing `FASTMAIL_*` still shows Connect — tokens are per user. |
| `FASTMAIL_TOKEN` | No | Fastmail JMAP API token for owner Mail. Server only. Missing token returns 401 “Connect Fastmail”, not 500. |
| `RAILWAY_API_TOKEN` | No | Railway account/project token so Junior can read deploy status and trigger Storykeep deploys. Create at Railway → Account → Tokens. Server only. |
| `GITHUB_TOKEN` | No | GitHub fine-grained PAT (repo + Actions read) so Junior can report commits, PRs, and CI. Server only. |
| `GITHUB_REPO` | No | Repo slug for Junior GitHub tools. Default `sb11b/Storykeep-`. |
| `CURSOR_API_KEY` | No | Cursor Cloud Agents API key so Junior can start Cloud Agent tasks from chat. Create at Cursor Dashboard → API Keys. Server only. |
| `CURSOR_AGENT_REPO` | No | Optional GitHub repo slug or full URL for spawned agents. Defaults to `GITHUB_REPO`. |
| `CURSOR_AGENT_BRANCH` | No | Default starting ref for Cloud Agents. Default `main`. |

Railway injects `RAILWAY_PROJECT_ID`, `RAILWAY_SERVICE_ID`, `RAILWAY_ENVIRONMENT_ID`, and `RAILWAY_PUBLIC_DOMAIN` on the storykeep service — Junior uses those automatically when the API token is set.

After deploy, `GET /api/health` reports `cursor_delegate: configured` when `CURSOR_API_KEY` is set (never exposes the key).

Generate a domain on the web service (**Settings → Networking → Generate domain**). Open that URL.

## 4. First login

The public demo account is closed. Create or use your own account on the sign-in screen. Production uses `stevebitsko@duck.com`.

Create your own account from the same screen if you prefer. Feeds keep importing in the background for a minute after deploy.

## 5. Custom domain

Settings → Networking → Custom domain. HTTPS is automatic. In production the app trusts Railway `X-Forwarded-Proto` and redirects leftover `http` to `https` (health checks on `/health` stay plain HTTP). Session cookies are marked `Secure` when `ENV` or `RAILWAY_ENVIRONMENT` is `production`.

## 6. Database security

- Prefer the Postgres **private** URL (`*.railway.internal`) for the app service when both run in the same Railway project.
- Use a dedicated application DB user — not the Postgres superuser — with only the privileges StoryKeep needs.
- Scheduled `pg_dump` uploads go to B2/S3; **encrypt dumps at rest** and keep encryption keys in Railway variables, not in the same folder as the dump artifact.

## 7. Backups on Railway

Chat photos live on the **storykeep** volume at `/app/var` (`DATA_DIR=/app/var`). Pre-volume media ids 404 if the file was never on that volume — do not migrate ghosts. Use **Export JSON**, S3/B2, or that volume for other app data.

## 8. GitHub vs CLI deploy (v2 stuck, `railway up` crashed)

Railway **GitHub** deploys build whatever is on **`sb11b/Storykeep-` `main`**. Cursor Origin can be ahead of GitHub. If `/api/health` shows an old `"build"` stamp (for example `junior-cursor-delegate-v2`), GitHub was not updated yet — not a Railway bug.

**Sync Origin → GitHub** (PowerShell in your Storykeep folder):

```powershell
.\scripts\sync-github.ps1
```

Or manually:

```powershell
git fetch origin
git merge origin/main
git push github main
```

Then in Railway: **storykeep web service** (not Postgres) → **Deployments** → **Redeploy** (or wait for auto-deploy).

**Verify after deploy:**

```text
GET https://storykeep-production.up.railway.app/api/health
```

Look for `"build": "junior-cursor-delegate-v3"` or newer (`junior-utc-stamp-v1`, `junior-deploy-reply-v1`, etc.).

### `railway up` from your PC

- **`railway up` uploads your local folder**, not GitHub. Old local code → old build stamp even if GitHub is current.
- When `railway link` asks for a service, choose the **storykeep web app**, **production** environment — **not** the Postgres database. Deploying the app Dockerfile to Postgres always crashes.
- If deploy shows **CRASHED** on the web service: open **Deploy Logs** on that failed deployment. Common causes:
  - Wrong service (Postgres selected)
  - `start.sh` saved with Windows CRLF (repo uses `.gitattributes` + Dockerfile strip; run `git pull` / re-sync)
  - Missing `DATABASE_URL` on the web service variables
- Prefer **GitHub redeploy** after `sync-github.ps1` when possible; use CLI when you need to ship un-pushed local changes.

Helper script: `scripts/railway-up.ps1`.
