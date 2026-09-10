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
| `SEED_DEMO` | No | Defaults on. May create a locked internal demo user and sample feeds. Password login for `steve@storykeep.local` is closed. |
| `S3_BUCKET` | No | Optional AWS S3 bucket if you are not using Backblaze |
| `B2_KEY_ID` | No | Backblaze application key ID |
| `B2_APPLICATION_KEY` | No | Backblaze application key (never put this in git or the browser) |
| `B2_BUCKET` | No | Backblaze bucket name |
| `B2_ENDPOINT` | No | S3-compatible endpoint, e.g. `https://s3.us-west-004.backblazeb2.com` |
| `B2_REGION` | No | Backblaze region, e.g. `us-west-004` |
| `XAI_API_KEY` | No | xAI API key (`xai-…`) for Listen, dictation, and the Grok chat bubble. Server only — never in the browser. |
| `XAI_CHAT_MODEL` | No | Chat model, default `grok-4` |

Generate a domain on the web service (**Settings → Networking → Generate domain**). Open that URL.

## 4. First login

The public demo account is closed. Create or use your own account on the sign-in screen. Production uses `stevebitsko@duck.com`.

Create your own account from the same screen if you prefer. Feeds keep importing in the background for a minute after deploy.

## 5. Custom domain

Settings → Networking → Custom domain. HTTPS is automatic. Session cookies are marked `Secure` when Railway sets `RAILWAY_ENVIRONMENT`.

## 6. Backups on Railway

The container filesystem is ephemeral. Use **Export JSON** from the library, attach an S3 bucket, or add a Railway volume mounted at `/app/var` and set `DATA_DIR=/app/var`.
