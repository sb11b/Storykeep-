# Junior shared chat memory — StoryKeep

**Store:** Railway Postgres (durable, searchable, shared)  
**Not store:** xAI (models only — generate replies; do not hold history)

Three clients talk to the same API → same DB:

1. StoryKeep (web)
2. Junior phone app
3. Windows overlay

Design sketch columns and CHECKs are the source of truth. This repo **reuses existing `users`** (do not apply a sketch `CREATE TABLE users` — it would drop required login columns). Sketch table names are prefixed:

| Sketch | StoryKeep table |
| --- | --- |
| `threads` | `junior_threads` |
| `messages` | `junior_thread_messages` |
| `memories` | `junior_memories` |
| `sessions` | `junior_sessions` |

Follow-up tables (not in the original sketch): `junior_projects`, `junior_agent_runs`.

Runnable SQL (copied into the container as `/app/migrations` so boot can apply them):

- `backend/migrations/001_junior_memory.sql`
- `backend/migrations/002_junior_projects.sql`

---

## Request flow (one turn)

1. Client sends `{ thread_id?, text, venue }` to `POST /api/v1/junior/messages`.
   - No `thread_id` → last `open` thread, or create one.
2. API inserts `junior_thread_messages` (`role=user`).
3. API loads last N messages, `thread.summary`, top `junior_memories`, and FTS hits when the text says “remember when…”.
4. If `XAI_API_KEY` is set, API calls xAI with that pack and inserts `role=junior`. Missing key → user row is still saved (`reply_status=stubbed_no_key`).
5. `updated_at` bumps; a short `summary` refresh runs every 8 messages.

Auth: same JWT / `sk_access` cookie as other Junior routes; every row is scoped by `user_id`.

---

## Junior phone app (equal citizen)

The phone app is **not** a second database. It is a client of this Memory API.

| Contract | Rule |
| --- | --- |
| Auth | Same StoryKeep user (`sk_access` or `Authorization: Bearer`). Same `user_id`. |
| Venue | Set `venue=phone` on `POST /threads`, `/messages`, `/threads/{id}/messages`. `venue_last` on the thread becomes `phone`. |
| Resume | `GET /threads` then `GET /threads/{id}/messages` or `GET /messages`, or `GET /search?q=` then `POST /threads/{id}/continue` (or keep posting to that thread). Those GETs (and `/search`, `/memories`, `/projects`) take `limit` plus `cursor` or `before_id`. History is server-side; failed posts stay on a local FIFO until replay. Continue posts replay on `/continue`. |
| Sessions | Optional `device_label` updates `junior_sessions` so overlay/phone last-seen is visible. |
| Voice | Finalized utterances still POST as messages with `venue=voice` (or `phone` if the app treats the turn as typed). Live audio stays on the device. |

There is no `/api/v1/junior/phone/*` namespace. Phone uses the same routes as StoryKeep and the Windows overlay.

StoryKeep ships the two callers in `backend/app/services/junior_shared_clients.py`:

| Client | venue | device_label | project slug |
| --- | --- | --- | --- |
| `phone_client` | `phone` | `junior-mobile` | `junior-phone` |
| `windows_client` | `windows` | `windows-overlay` | `windows-overlay` |

Both post to `POST /api/v1/junior/messages` (or `/threads/{id}/messages`) and resume with `POST /threads/{id}/continue`. They read with `GET /threads`, `GET /messages`, `GET /threads/{id}/messages`, `GET /search`, `GET /memories`, `GET /projects`, and `GET /agent-context` (`limit` plus `cursor` or `before_id` on the list routes; `X-Next-Cursor` when another page exists). Login required. A demo account gets 403. The callers retry 401/403/5xx (and transport errors) with backoff, then raise a short user-visible error on the phone and Windows overlay surfaces — a failed post is never dropped silently. Failed writes stay on a local FIFO and replay in order after a successful login with the same auth. Continue posts replay on `/continue`, not `/messages`.

Seed project slug: `junior-phone` (kept for API stability). Display name **Junior mobile**. Repo: [https://cursor.com/codebase/steve-bitsko/junior-mobile](https://cursor.com/codebase/steve-bitsko/junior-mobile) (Expo phone client; `venue=phone`; StoryKeep `/api/v1/junior/*`).

---

## Project registry + Cursor agents

Junior can start Cursor agents with a **full picture** — repo + memory — not StoryKeep-only chat text.

```
┌─────────────┐   ┌──────────────┐   ┌────────────────┐
│ StoryKeep   │   │ Junior phone │   │ Windows overlay│
│ venue=      │   │ venue=phone  │   │ venue=windows  │
│ storykeep   │   │              │   │                │
└──────┬──────┘   └──────┬───────┘   └────────┬───────┘
       │                 │                    │
       │     HTTPS + same user_id             │
       └─────────────────┼────────────────────┘
                         ▼
              ┌─────────────────────┐
              │  Junior Memory API  │
              │  threads / search   │
              │  projects / agents  │
              └──────────┬──────────┘
                         │
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
    Railway Postgres   xAI Grok     Cursor agent
    history+projects   inference    (context pack;
                                    this slice does
                                    not call Cursor)
```

### Seed projects (owner `angry.tune8751@fastmail.com` on API boot)

| slug | kind | repo_url | notes |
| --- | --- | --- | --- |
| `storykeep` | app | `https://cursor.com/codebase/steve-bitsko/Storykeep` | Memory API lives here for now |
| `junior-phone` | app | `https://cursor.com/codebase/steve-bitsko/junior-mobile` | Junior mobile (Expo); `venue=phone`; `/api/v1/junior/*` |
| `windows-overlay` | overlay | (null / placeholder) | Until a repo exists |

Boot also seeds durable **decisions** in `junior_memories`: Railway Postgres is source of truth; xAI is inference only; three venues share one API; Junior can launch Cursor agents with a context pack.

### How Junior uses agent-context before a Cursor agent

1. `GET /api/v1/junior/projects` — pick a slug (or upsert one).
2. `GET /api/v1/junior/agent-context?project=storykeep&q=` — pack is `{ project, thread_summary, recent_messages, memories, search_hits, launch_hint }`. Thread is last `open` (or `thread_id=`).
3. `POST /api/v1/junior/agents` `{ project_slug, prompt, thread_id? }` — rebuilds that pack, inserts `junior_agent_runs` with `status=context_ready`, **does not** call the Cursor Cloud Agents API in this slice (`called_cursor_api: false`, `cursor_agent_id` null).

Use `launch_hint` + the pack as the agent prompt context so a StoryKeep-only paste is not the whole brief.

---

## Endpoints

See the README “Junior shared chat memory” section.
