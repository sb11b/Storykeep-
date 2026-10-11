# Junior app — completion plan

Recreated 2026-10-11, updated 2026-10-11. Ground truth: GitHub main (highest merged PR #163, commit 7c0c591).
This is the working plan for finishing the Junior app. One slice per branch; merge only after the Hermes code reviewer passes.

## Where we are (done)

**Backend Junior API — complete.** ~135 routes behind `require_user`:
- chats, jobs (task protocol, #151: create/patch/delete/run + cron `run_due_jobs`), memory (standing note)
- projects, threads, messages, memories, agents, sessions, search, documents (+ binary file upload/download, #150)
- agent-context packs (rebuild + pin), SSE event stream with resumable replay (#152)
- service-token auth (#147): machine clients authenticate as owner with `SERVICE_TOKEN`
- explicitly-referenced documents injected into chat context (#153)

**Web venue — complete.** junior-jobs-panel and junior-memory-panel (imported by grok-bubble.tsx) plus junior-mic controls (grok-pane.tsx) are wired to their client functions in `frontend/src/lib/api.ts` (juniorJobs/createJuniorJob/patchJuniorJob/runJuniorJob, juniorMemory/putJuniorMemory).

**Android — complete client (slices 1-5, merged through #162).** Three Compose screens (Home / Conversation / Stories) against a Retrofit/OkHttp client with `SERVICE_TOKEN` via BuildConfig; real Talk (`/api/v1/stt` + `/api/v1/tts`), real Conversation (chats, threads, messages, shared-memory projects), real Stories (shared-memory documents), release signing with `versionCode` 2 / `versionName` '0.1.0' (R8). Talk's product lock is preserved.

**junior-mobile (Expo) — DROPPED (slice 6, decision 2026-10-11).** No repo under sb11b, and the docs treat the phone venues as one venue — there is no `/api/v1/junior/phone/*` namespace; the phone client maps to venue `phone` / device_label `junior-mobile` / project slug `junior-phone` (docs/junior_shared_memory.md). With Android a complete client against the identical API, a second Expo app would be pure duplication. Android is the phone client. The `phone` venue and the seed row stay in place and the API stays ready if Steve reconsiders.

**Windows overlay — DEFERRED indefinitely (slice 7, decision 2026-10-11).** Verified from the repo: (1) the backend `overlay` router (`backend/app/routers/overlay.py`, services `overlay_pack.py` / `overlay_search.py`) is the *notes* overlay — article annotations, `/storykeep-notes`, note revisions, corrections, media, Obsidian vault import and `/export/obsidian-pack` — not a desktop quick-capture/quick-chat surface. (2) `windows` is only a seeded venue in `VENUES` (`backend/app/services/junior_shared_memory.py`); there is no windows-specific API namespace — the windows client shares the generic `/api/v1/junior/*` routes, exactly like the other venues. (3) No Windows overlay client repo exists under sb11b (`gh repo list sb11b` shows only Storykeep-, meridian, Storykeep, storykeep--, claude-hub, mine). Building a desktop client against the generic Memory API is possible at any time — this is a deferral, not a block. The `windows` venue and the `windows-overlay` seed project row stay in place. Reopens when Steve wants a desktop quick-capture/quick-chat surface (that would need new backend routes, not just a client) or names a client repo to build.

## Remaining slices, in order

Each is one `cursor/*` branch: implement → review → PR → Hermes code review → merge → Railway.

### Decided and merged (slices 1-5 + decisions 6-7)

1. **Android network layer.** Retrofit/OkHttp client; base URL + `SERVICE_TOKEN` via BuildConfig (never commit the token); 401 handling. Turns the shell into a real client.
2. **Android real Talk.** Replaced the fake transcript: mic → `POST /api/v1/stt` (clip) or the realtime websocket; reply → `POST /api/v1/tts` playback. The product lock is kept.
3. **Android Conversation.** `GET /api/v1/junior/chats`, thread messages, `POST /messages` send. Placeholder data killed.
4. **Android Stories.** `GET /api/v1/junior/projects`, documents, files. Local save stays as offline cache.
5. **Android release hygiene.** Signing config, `versionCode` 2, proguard rules, `versionName` off "-shell".
6. **junior-mobile decision — DROPPED.** The Expo venue was dropped; Android is the phone client (rationale above). Docs-only decision, no client built.
7. **Windows overlay decision — DEFERRED indefinitely.** The `overlay` backend is the notes overlay, not a desktop quick-capture surface; there is no windows-specific API and no client repo. The venue stays seeded and a client can be built against the generic Memory API any time (rationale above). Docs-only decision, no client built.

### Remaining

(none — all 7 slices resolved; the completion plan is closed)

## Notes

- Android cannot be compiled on this host (no Android SDK, same as Docker). Kotlin is written and reviewed here; Steve builds in Android Studio.
- The ledger Junior sees in chat is the `junior-ledger` DB document (capped 1,200 chars), seeded from `backend/app/seed.py` and updatable via `POST /api/v1/junior/documents`.

## Project state (plan closed 2026-10-11)

All 7 slices are resolved. What the Junior app is now:

- **Web (this repo) — complete.** Full Junior API (~135 routes behind `require_user` + service-token auth) and the web panels (jobs, memory, mic) wired in `frontend/src`.
- **Android — complete real client (slices 1-5).** Retrofit/OkHttp against the same API, real Talk (STT/TTS), real Conversation and Stories, release signing. Steve builds in Android Studio (no SDK here).
- **junior-mobile (Expo) — DROPPED (slice 6).** Android is the phone client; `venue=phone` / `junior-phone` stay seeded. Reopens only if Steve wants a second phone app.
- **Windows overlay — DEFERRED indefinitely (slice 7).** The backend `overlay` router is the notes overlay (article annotations, Obsidian import/packs, media, corrections), not a desktop capture surface; there is no windows-specific API and no client repo. The `windows` venue stays seeded. Reopens when a desktop quick-capture/quick-chat surface is wanted (new backend routes needed) or a client repo is named — a client against the generic Memory API can be built any time.

Nothing is left to build. Future work is either new backend features or a client against the finished API.
