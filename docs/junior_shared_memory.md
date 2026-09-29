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
| Resume | `GET /threads` or `GET /threads/{id}`, then `GET /threads/{id}/messages` or `GET /messages` or `GET /messages/{id}`, or `GET /search?q=` or `GET /search/{id}` then `POST /threads/{id}/continue` (or `GET /threads/{id}/continue`, or keep posting to that thread). Those GETs (and `/search`, `/search/{id}`, `/memories`, `/memories/{id}`, `/projects`, `/projects/{slug}`, `/sessions`, `/sessions/{id}`, `/agents/{id}`, `/agent-context/{slug}`, `/threads/{id}/messages/{id}`, `/threads/{id}/continue`, `/threads/{id}/memories`, `/threads/{id}/memories/{id}`, `/threads/{id}/agents/{id}`, `/threads/{id}/agents`, `/threads/{id}/search/{id}`, `/threads/{id}/search`, `/threads/{id}/agent-context/{slug}`, `/projects/{slug}/search`, `/projects/{slug}/agents`) and continue history take `limit` plus `cursor` or `before_id`. History is server-side; failed posts, memory writes, memory updates, message updates, session heartbeats, session updates, thread creates, thread title/status updates, project updates, agent updates, search-hit updates, agent-context updates, thread-message updates, project-agent updates, project-agent launches, thread-memory updates, thread-memory creates, and thread-agent updates, thread-agent launches, thread search-hit updates, thread searches, and project searches stay on a local FIFO until replay. Continue posts replay on `/continue`. Thread creates replay on `/threads`. Thread updates replay on `/threads/{id}`. Project updates replay on `/projects/{slug}`. Memory updates replay on `/memories/{id}`. Session updates replay on `/sessions/{id}`. Message updates replay on `/messages/{id}`. Agent updates replay on `/agents/{id}`. Search-hit updates replay on `/search/{id}`. Agent-context updates replay on `/agent-context/{slug}`. Thread-message updates replay on `/threads/{id}/messages/{id}`. Thread-memory updates replay on `/threads/{id}/memories/{id}`. Thread-agent updates replay on `/threads/{id}/agents/{id}`. Thread-agent launches replay on `/threads/{id}/agents`. Project-agent launches replay on `/projects/{slug}/agents`. Thread-memory creates replay on `/threads/{id}/memories`. Thread searches replay on `/threads/{id}/search`. Thread-context updates replay on `/threads/{id}/agent-context/{slug}`. Project searches replay on `/projects/{slug}/search`. || Sessions | `GET /sessions`, `GET /sessions/{id}`, `POST /sessions` (heartbeat), and `POST /sessions/{id}` (update). `device_label` updates `junior_sessions` so overlay/phone last-seen is visible. || Voice | Finalized utterances still POST as messages with `venue=voice` (or `phone` if the app treats the turn as typed). Live audio stays on the device. |

There is no `/api/v1/junior/phone/*` namespace. Phone uses the same routes as StoryKeep and the Windows overlay.

StoryKeep ships the two callers in `backend/app/services/junior_shared_clients.py`:

| Client | venue | device_label | project slug |
| --- | --- | --- | --- |
| `phone_client` | `phone` | `junior-mobile` | `junior-phone` |
| `windows_client` | `windows` | `windows-overlay` | `windows-overlay` |

Both post to `POST /api/v1/junior/messages` (or `/threads/{id}/messages`) and resume with `POST /threads/{id}/continue` (`limit` plus `cursor` or `before_id` on history). They open threads with `POST /threads`. Thread title/status updates go to `POST /threads/{id}` and replay on that route. They write durable facts with `POST /memories`. Memory updates go to `POST /memories/{id}` and replay on that route. Message updates go to `POST /messages/{id}` and replay on that route. Agent-run updates go to `POST /agents/{id}` and replay on that route. Search-hit updates go to `POST /search/{id}` and replay on that route. Agent-context updates go to `POST /agent-context/{slug}` and replay on that route. Thread-context updates go to `POST /threads/{id}/agent-context/{slug}` and replay on that route (not `POST /agent-context/{slug}`). Thread-message updates go to `POST /threads/{id}/messages/{id}` and replay on that route. Project-agent updates go to `POST /projects/{slug}/agents/{id}` and replay on that route. Project-agent launches go to `POST /projects/{slug}/agents` and replay on that route (not `POST /agents`). Thread-memory updates go to `POST /threads/{id}/memories/{id}` and replay on that route. Thread-memory creates go to `POST /threads/{id}/memories` and replay on that route (not `POST /memories`). Thread-agent updates go to `POST /threads/{id}/agents/{id}` and replay on that route (not `POST /agents/{id}` and not `POST /projects/{slug}/agents/{id}`). Thread-agent launches go to `POST /threads/{id}/agents` and replay on that route (not `POST /agents` and not `POST /projects/{slug}/agents`). Thread search-hit updates go to `POST /threads/{id}/search/{id}` and replay on that route (not `POST /search/{id}`). Thread searches go to `POST /threads/{id}/search` and replay on that route (not `GET /search` and not `POST /search/{id}`). Project searches go to `POST /projects/{slug}/search` and replay on that route (not `GET /search`, not `POST /threads/{id}/search`, and not `POST /search/{id}`). They also POST `/projects`, `/projects/{slug}`, `/agents`, `/sessions`, and `/sessions/{id}`. They read with `GET /threads`, `GET /threads/{id}`, `GET /messages`, `GET /messages/{id}`, `GET /threads/{id}/messages`, `GET /threads/{id}/messages/{id}`, `GET /threads/{id}/continue`, `GET /threads/{id}/memories`, `GET /threads/{id}/memories/{id}`, `GET /threads/{id}/agents`, `GET /threads/{id}/agents/{id}`, `GET /threads/{id}/search/{id}`, `GET /threads/{id}/search`, `GET /projects/{slug}/search`, `GET /search`, `GET /search/{id}`, `GET /memories`, `GET /memories/{id}`, `GET /projects`, `GET /projects/{slug}`, `GET /projects/{slug}/agents`, `GET /projects/{slug}/agents/{id}`, `GET /agents`, `GET /agents/{id}`, `GET /sessions`, `GET /sessions/{id}`, `GET /agent-context`, and `GET /agent-context/{slug}`, `GET /threads/{id}/agent-context/{slug}` (`limit` plus `cursor` or `before_id` on the list routes; `X-Next-Cursor` when another page exists). Login required. A demo account gets 403. The callers retry 401/403/5xx (and transport errors) with backoff, then raise a short user-visible error on the phone and Windows overlay surfaces — a failed post is never dropped silently. Failed writes stay on a local FIFO and replay in order after a successful login with the same auth. Continue posts replay on `/continue`, not `/messages`. Message updates replay on `/messages/{id}`, not `/messages`. Thread-message updates replay on `/threads/{id}/messages/{id}`, not `/messages/{id}`. Session heartbeats replay on `/sessions`. Session updates replay on `/sessions/{id}`. Thread creates replay on `/threads`. Project updates replay on `/projects/{slug}`. Memory updates replay on `/memories/{id}`. Agent updates replay on `/agents/{id}`, not `/agents`. Search-hit updates replay on `/search/{id}`, not `/search`. Agent-context updates replay on `/agent-context/{slug}`, not GET `/agent-context`. Thread-memory updates replay on `/threads/{id}/memories/{id}`, not `/memories/{id}`. Thread-agent updates replay on `/threads/{id}/agents/{id}`, not `/agents/{id}`. Thread-agent launches replay on `/threads/{id}/agents`, not `POST /agents` and not `POST /projects/{slug}/agents`. Thread search-hit updates replay on `/threads/{id}/search/{id}`, not `POST /search/{id}`. Thread searches replay on `/threads/{id}/search`, not `GET /search` and not `POST /search/{id}`. Thread-context updates replay on `/threads/{id}/agent-context/{slug}`, not `POST /agent-context/{slug}`. Project searches replay on `/projects/{slug}/search`, not `GET /search`, not `POST /threads/{id}/search`, and not `POST /search/{id}`. Thread-memory creates replay on `/threads/{id}/memories`, not `POST /memories`. Project-agent launches replay on `/projects/{slug}/agents`, not `POST /agents`.Seed project slug: `junior-phone` (kept for API stability). Display name **Junior mobile**. Repo: [https://cursor.com/codebase/steve-bitsko/junior-mobile](https://cursor.com/codebase/steve-bitsko/junior-mobile) (Expo phone client; `venue=phone`; StoryKeep `/api/v1/junior/*`).

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
2. `GET /api/v1/junior/agent-context?project=storykeep&q=` or `GET /agent-context/{slug}` — pack is `{ project, thread_summary, recent_messages, memories, search_hits, launch_hint }`. Thread is last `open` (or `thread_id=`). `POST /agent-context/{slug}` pins `q` / `thread_id` on that project. `GET /threads/{id}/messages/{id}` loads one owned message in that thread. `POST /threads/{id}/messages/{id}` updates that message. `GET /threads/{id}/continue` loads continue history without posting a turn. `GET /threads/{id}/memories` pages memories sourced from that thread. `POST /threads/{id}/memories` saves one on that thread. `GET /threads/{id}/memories/{id}` loads one memory sourced from that thread. `POST /threads/{id}/memories/{id}` updates it. `GET /projects/{slug}/agents` pages agent runs on that project (`limit` plus `cursor` or `before_id`). `POST /projects/{slug}/agents` records a launch on that project. `GET /projects/{slug}/agents/{id}` loads one agent run on that project. `POST /projects/{slug}/agents/{id}` updates it. `GET /threads/{id}/agents` pages agent runs recorded on that thread (`limit` plus `cursor` or `before_id`). `POST /threads/{id}/agents` records a launch on that thread. `GET /threads/{id}/agents/{id}` loads one agent run recorded on that thread. `POST /threads/{id}/agents/{id}` updates it. `GET /threads/{id}/search/{id}` loads one search hit on that thread. `POST /threads/{id}/search/{id}` updates it. `GET /threads/{id}/search` pages search hits on that thread (`q`, `limit`, `cursor` or `before_id`). `POST /threads/{id}/search` runs that search. `GET /threads/{id}/agent-context/{slug}` loads one context pack for that thread and project. `POST /threads/{id}/agent-context/{slug}` pins `q` and that thread on the project. `GET /projects/{slug}/search` pages search hits on that project (`q`, `limit`, `cursor` or `before_id`). `POST /projects/{slug}/search` runs that search.3. `GET /api/v1/junior/agents` — that user’s recorded runs (`limit`, `cursor` or `before_id`, optional `project=`). `GET /agents/{id}` loads one owned run.
4. `POST /api/v1/junior/agents` `{ project_slug, prompt, thread_id? }` — rebuilds that pack, inserts `junior_agent_runs` with `status=context_ready`, **does not** call the Cursor Cloud Agents API in this slice (`called_cursor_api: false`, `cursor_agent_id` null).

Use `launch_hint` + the pack as the agent prompt context so a StoryKeep-only paste is not the whole brief.

---

## Endpoints

See the README “Junior shared chat memory” section.
