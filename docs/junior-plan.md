# Junior app — completion plan

Recreated 2026-10-11, updated 2026-10-11. Ground truth: GitHub main (highest merged PR #162, commit 0b87eaa).
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

**Windows overlay — backend only.** `overlay.py`, `overlay_pack.py`, `overlay_search.py` exist; no client repo.

## Remaining slices, in order

Each is one `cursor/*` branch: implement → review → PR → Hermes code review → merge → Railway.

### Decided and merged (slices 1-5 + decision 6)

1. **Android network layer.** Retrofit/OkHttp client; base URL + `SERVICE_TOKEN` via BuildConfig (never commit the token); 401 handling. Turns the shell into a real client.
2. **Android real Talk.** Replaced the fake transcript: mic → `POST /api/v1/stt` (clip) or the realtime websocket; reply → `POST /api/v1/tts` playback. The product lock is kept.
3. **Android Conversation.** `GET /api/v1/junior/chats`, thread messages, `POST /messages` send. Placeholder data killed.
4. **Android Stories.** `GET /api/v1/junior/projects`, documents, files. Local save stays as offline cache.
5. **Android release hygiene.** Signing config, `versionCode` 2, proguard rules, `versionName` off "-shell".
6. **junior-mobile decision — DROPPED.** The Expo venue was dropped; Android is the phone client (rationale above). Docs-only decision, no client built.

### Remaining

7. **Windows overlay decision.** Build a client, or defer indefinitely. Steve decides.

## Notes

- Android cannot be compiled on this host (no Android SDK, same as Docker). Kotlin is written and reviewed here; Steve builds in Android Studio.
- The ledger Junior sees in chat is the `junior-ledger` DB document (capped 1,200 chars), seeded from `backend/app/seed.py` and updatable via `POST /api/v1/junior/documents`.
