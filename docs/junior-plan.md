# Junior app — completion plan

Recreated 2026-10-11. Ground truth: GitHub main (highest merged PR #153, commit 8c42294).
This is the working plan for finishing the Junior app. One slice per branch; merge only after the Hermes code reviewer passes.

## Where we are (done)

**Backend Junior API — complete.** ~135 routes behind `require_user`:
- chats, jobs (task protocol, #151: create/patch/delete/run + cron `run_due_jobs`), memory (standing note)
- projects, threads, messages, memories, agents, sessions, search, documents (+ binary file upload/download, #150)
- agent-context packs (rebuild + pin), SSE event stream with resumable replay (#152)
- service-token auth (#147): machine clients authenticate as owner with `SERVICE_TOKEN`
- explicitly-referenced documents injected into chat context (#153)

**Web venue — complete.** junior-jobs-panel and junior-memory-panel (imported by grok-bubble.tsx) plus junior-mic controls (grok-pane.tsx) are wired to their client functions in `frontend/src/lib/api.ts` (juniorJobs/createJuniorJob/patchJuniorJob/runJuniorJob, juniorMemory/putJuniorMemory).

**Android — shell only.** Three Compose screens (Home / Conversation / Stories), Talk session core with the product lock (Talk dies on Type/End/leave/lock/network-loss). Local fake transcript. No network layer, no auth, no real voice.

**junior-mobile (Expo) — does not exist.** No repo under sb11b. Seeded as venue `junior-phone` in the DB.

**Windows overlay — backend only.** `overlay.py`, `overlay_pack.py`, `overlay_search.py` exist; no client repo.

## Remaining slices, in order

Each is one `cursor/*` branch: implement → review → PR → Hermes code review → merge → Railway.

1. **Android network layer.** Retrofit/OkHttp client; base URL + `SERVICE_TOKEN` via BuildConfig (never commit the token); 401 handling. Turns the shell into a real client.
2. **Android real Talk.** Replace the fake transcript: mic → `POST /api/v1/stt` (clip) or the realtime websocket; reply → `POST /api/v1/tts` playback. Keep the product lock.
3. **Android Conversation.** `GET /api/v1/junior/chats`, thread messages, `POST /messages` send. Kill placeholder data.
4. **Android Stories.** `GET /api/v1/junior/projects`, documents, files. Local save stays as offline cache.
5. **Android release hygiene.** Signing config, `versionCode` 2, proguard rules, `versionName` off "-shell".
6. **junior-mobile decision.** Build the Expo client against the finished API, or drop the venue and let Android be the phone client (docs already treat them as one venue). Steve decides.
7. **Windows overlay decision.** Build a client, or defer indefinitely. Steve decides.

## Notes

- Android cannot be compiled on this host (no Android SDK, same as Docker). Kotlin is written and reviewed here; Steve builds in Android Studio.
- The ledger Junior sees in chat is the `junior-ledger` DB document (capped 1,200 chars), seeded from `backend/app/seed.py` and updatable via `POST /api/v1/junior/documents`.
