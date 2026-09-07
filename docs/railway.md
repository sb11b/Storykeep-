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

Railway’s URL looks like `postgresql://…`. Storykeep rewrites that to SQLAlchemy’s `postgresql+psycopg2://` form automatically.

## 3. Variables

| Variable | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` | Yes | From the Postgres plugin |
| `SECRET_KEY` | Recommended | Any long random string. If you skip it, a stable key is derived from the database URL. |
| `SEED_DEMO` | No | Defaults on. Creates `steve@storykeep.local` / `commonplace` and sample feeds on first boot. Set `0` after you have your own account. |
| `S3_BUCKET` | No | Optional off-site backup target |

Generate a domain on the web service (**Settings → Networking → Generate domain**). Open that URL.

## 4. First login

Demo account (when `SEED_DEMO` is on):

- email: `steve@storykeep.local`
- password: `commonplace`

Create your own account from the same screen if you prefer. Feeds keep importing in the background for a minute after deploy.

## 5. Custom domain

Settings → Networking → Custom domain. HTTPS is automatic. Session cookies are marked `Secure` when Railway sets `RAILWAY_ENVIRONMENT`.

## 6. Backups on Railway

The container filesystem is ephemeral. Use **Export JSON** from the library, attach an S3 bucket, or add a Railway volume mounted at `/app/var` and set `DATA_DIR=/app/var`.
