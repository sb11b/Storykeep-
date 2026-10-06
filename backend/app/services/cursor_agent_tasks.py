"""Sequenced task prompt strings for the Cursor Cloud Agent.

Each SEQ_*_TASK is a self-contained prompt for a numbered sequence step.
POLISH_2_TASK is the special #2 polish prompt.  _POLISH_2_RE matches
messages that request #2 polish.  These are pure string/regex constants
with no runtime dependencies beyond ``re``.
"""

import re

_POLISH_2_RE = re.compile(
    r"\b(?:go ahead and\s+)?(?:start|begin|launch|do)\b.{0,80}(?:sequenced\s+)?#?\s*2\b.{0,40}\bpolish\b"
    r"|\b(?:sequenced\s+)?#?\s*2\s+polish\b",
    re.I | re.S,
)

POLISH_2_TASK = """Sequenced #2 polish only, on GitHub main of sb11b/Storykeep- (StoryKeep).

The shared Junior memory slice is already deployed from GitHub main. Do not merge Cursor PR #2 on steve-bitsko/Storykeep. Do not re-run migrations. Do not change the owner email (angry.tune8751@fastmail.com).

Polish the shared-memory API that is already in this repo:
- Auth: /api/v1/junior/* stays behind require_user. Demo accounts stay 403.
- Env: the container must include backend/migrations so boot can apply 001_junior_memory.sql then 002_junior_projects.sql. DATABASE_URL stays ${{Postgres.DATABASE_URL}}.
- Smoke: tests that those two SQL files are idempotent, and that the owner seed writes storykeep, junior-phone (display Junior mobile, repo https://cursor.com/codebase/steve-bitsko/junior-mobile), and windows-overlay.

Stay on this repository. The starting ref is main. Commit on a cursor/* branch. Do not create a new project.
"""


def polish_2_task(message: str) -> str | None:
    if _POLISH_2_RE.search(message or ""):
        return POLISH_2_TASK
    return None


_NUM_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "twenty-one": 21,
    "twenty-two": 22,
    "twenty-three": 23,
    "twenty-four": 24,
    "twenty-five": 25,
    "twenty-six": 26,
    "twenty-seven": 27,
    "twenty-eight": 28,
    "twenty-nine": 29,
    "thirty": 30,
}
_SEQ_MENTION_RE = re.compile(
    r"\bsequenc(?:e|ed)\s+(?:number\s+)?#?\s*"
    r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|thirty|twenty-nine|twenty-eight|twenty-seven|twenty-six|twenty-five|twenty-four|twenty-three|twenty-two|twenty-one|twenty)\b"
    r"|\b(?:sequenced\s+)?#\s*(\d+)\b",
    re.I,
)
_NEXT_STEP_RE = re.compile(
    r"\b(?:send|start)(?:\s+the)?\s+next\s+step\b"
    r"|\bgo ahead and (?:send|start)\b"
    r"|\bmove on to the (?:next|nest) step\b"
    r"|\bsequenc(?:e|ed)\s+(?:number\s+)?#?\s*"
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|thirty|twenty-nine|twenty-eight|twenty-seven|twenty-six|twenty-five|twenty-four|twenty-three|twenty-two|twenty-one|twenty)\b",
    re.I,
)

SEQ_58_TASK = """Sequenced #58 — next after junior-client-project-thread-memory-note-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46, #47, #48, #49, #50, #51, #52, #53, #54, #55, #56, or #57).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #57 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main. CodeRabbit reviews it. Bugbot is off. Do not comment bugbot run. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/threads/{thread_id}/memory to append the standing note; the original text stays
- GET /projects/{slug}/threads/{thread_id}/memory loads that note when the thread is on the project
- Failed appends replay on POST /projects/{slug}/threads/{thread_id}/memory, not POST /memory, not PUT /memory, not POST /memories, not POST /threads/{id}/memory, and not POST /projects/{slug}/threads/{thread_id}/memories
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-thread-memory-note-get-v1

Your job (#58):
1. Both clients POST /projects/{slug}/memory to append text to the standing note for that project. The original text stays. Failed writes stay on the FIFO and replay on that same route (not POST /memory, not PUT /memory, not POST /memories, not POST /threads/{id}/memory, not POST /projects/{slug}/threads/{thread_id}/memory, and not POST /projects/{slug}/memories). Same auth rule. No silent drop. 404 if the project is missing.
2. Both clients call GET /projects/{slug}/memory (same auth). 404 if the project is missing. Still no public routes.
3. Keep SQL idempotent; no DROP TABLE. No new public routes.
4. Extend smoke tests for project memory-note replay, project memory-note GET, and 403. Keep existing tests green.
5. Health stamp: junior-client-project-memory-note-get-v1
6. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_57_TASK = """Sequenced #57 — next after junior-client-thread-memory-note-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46, #47, #48, #49, #50, #51, #52, #53, #54, #55, or #56).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #56 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main. CodeRabbit reviews it. Bugbot is off. Do not comment bugbot run. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /threads/{id}/memory to append the standing note; the original text stays
- GET /threads/{id}/memory loads that note when the thread belongs to the user
- Failed appends replay on POST /threads/{id}/memory, not POST /memory, not PUT /memory, not POST /memories, and not POST /threads/{id}/memories
- require_user; demo 403; no new public routes
- Health stamp junior-client-thread-memory-note-get-v1

Your job (#57):
1. Both clients POST /projects/{slug}/threads/{thread_id}/memory to append text to the standing note for that thread on the project. The original text stays. Failed writes stay on the FIFO and replay on that same route (not POST /memory, not PUT /memory, not POST /memories, not POST /threads/{id}/memory, and not POST /projects/{slug}/threads/{thread_id}/memories). Same auth rule. No silent drop. 404 if the project is missing or the thread is not on that project.
2. Both clients call GET /projects/{slug}/threads/{thread_id}/memory (same auth). 404 in those same cases. Still no public routes.
3. Keep SQL idempotent; no DROP TABLE. No new public routes.
4. Extend smoke tests for project-thread memory-note replay, project-thread memory-note GET, and 403. Keep existing tests green.
5. Health stamp: junior-client-project-thread-memory-note-get-v1
6. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_56_TASK = """Sequenced #56 — next after junior-client-memory-note-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46, #47, #48, #49, #50, #51, #52, #53, #54, or #55).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #55 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main. CodeRabbit reviews it. Bugbot is off. Do not comment bugbot run. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /memory to append the standing note; the original text stays
- GET /memory loads that note
- Failed appends replay on POST /memory, not PUT /memory and not POST /memories
- require_user; demo 403; no new public routes
- Health stamp junior-client-memory-note-get-v1

Your job (#56):
1. Both clients POST /threads/{id}/memory to append text to the standing note for that thread. The original text stays. Failed writes stay on the FIFO and replay on that same route (not POST /memory, not PUT /memory, not POST /memories, and not POST /threads/{id}/memories). Same auth rule. No silent drop. 404 if the thread is missing.
2. Both clients call GET /threads/{id}/memory (same auth). 404 if the thread is missing. Still no public routes.
3. Keep SQL idempotent; no DROP TABLE. No new public routes.
4. Extend smoke tests for thread memory-note replay, thread memory-note GET, and 403. Keep existing tests green.
5. Health stamp: junior-client-thread-memory-note-get-v1
6. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_55_TASK = """Sequenced #55 — next after junior-client-project-sessions-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46, #47, #48, #49, #50, #51, #52, #53, or #54).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #54 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main. CodeRabbit reviews it. Bugbot is off. Do not comment bugbot run. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/sessions; failed heartbeats replay on that route
- GET /projects/{slug}/sessions pages sessions whose venue matches a thread on that project
- GET and PUT /memory already exist for the standing note
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-sessions-page-v1

Your job (#55):
1. Both clients POST /memory to append text to the standing note. The original text stays. Failed writes stay on the FIFO and replay on that same route (not PUT /memory and not POST /memories). Same auth rule. No silent drop.
2. Both clients call GET /memory (same auth). Still no public routes.
3. Keep SQL idempotent; no DROP TABLE. No new public routes.
4. Extend smoke tests for memory-note replay, memory-note GET, and 403. Keep existing tests green.
5. Health stamp: junior-client-memory-note-get-v1
6. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_54_TASK = """Sequenced #54 — next after junior-client-project-session-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46, #47, #48, #49, #50, #51, #52, or #53).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #53 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/sessions/{session_id}; failed updates replay on that route
- GET /projects/{slug}/sessions/{session_id} loads one session whose venue matches a thread on that project
- POST /projects/{slug}/threads/{thread_id}/sessions and GET /projects/{slug}/threads/{thread_id}/sessions already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-session-get-v1

Your job (#54):
1. Both clients POST /projects/{slug}/sessions to record a session on that project. Failed writes stay on the FIFO and replay on that same route (not POST /sessions, not POST /threads/{id}/sessions, not POST /projects/{slug}/sessions/{session_id}, and not POST /projects/{slug}/threads/{thread_id}/sessions). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/sessions to page sessions on that project (limit/cursor or before_id). A session is on the project when its venue matches a thread tied to the project. Same require_user rules. 404 if the project is missing. Still no public routes.
3. Both clients call GET /projects/{slug}/sessions (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-sessions replay, project-sessions GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-sessions-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_53_TASK = """Sequenced #53 — next after junior-client-project-thread-sessions-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46, #47, #48, #49, #50, #51, or #52).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #52 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/threads/{thread_id}/sessions; failed heartbeats replay on that route
- GET /projects/{slug}/threads/{thread_id}/sessions pages sessions on that thread (venue matches the thread)
- POST /sessions/{id} and GET /sessions/{id} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-thread-sessions-page-v1

Your job (#53):
1. Both clients POST /projects/{slug}/sessions/{session_id} to update a session on that project. Failed writes stay on the FIFO and replay on that same route (not POST /sessions/{id}, not POST /threads/{id}/sessions/{id}, and not POST /projects/{slug}/threads/{thread_id}/sessions/{session_id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/sessions/{session_id} for one session on that project. The session venue must match a thread tied to the project. Same require_user rules. 404 if the project is missing or the session is not on that project. Still no public routes.
3. Both clients call GET /projects/{slug}/sessions/{session_id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-session replay, project-session GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-session-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_52_TASK = """Sequenced #52 — next after junior-client-project-thread-session-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46, #47, #48, #49, #50, or #51).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #51 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/threads/{thread_id}/sessions/{session_id}; failed updates replay on that route
- GET /projects/{slug}/threads/{thread_id}/sessions/{session_id} loads one session on that thread (venue matches the thread)
- POST /threads/{id}/sessions and GET /threads/{id}/sessions already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-thread-session-get-v1

Your job (#52):
1. Both clients POST /projects/{slug}/threads/{thread_id}/sessions to record a session on that project thread. Failed writes stay on the FIFO and replay on that same route (not POST /threads/{id}/sessions, not POST /sessions, and not POST /projects/{slug}/threads/{thread_id}/sessions/{session_id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/threads/{thread_id}/sessions to page sessions on that thread (limit/cursor or before_id). The thread must be on the project. A session is on the thread when its venue matches the thread's last venue. Same require_user rules. 404 if the project is missing or the thread is not on the project. Still no public routes.
3. Both clients call GET /projects/{slug}/threads/{thread_id}/sessions (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-thread-sessions replay, project-thread-sessions GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-thread-sessions-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_51_TASK = """Sequenced #51 — next after junior-client-thread-sessions-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46, #47, #48, #49, or #50).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #50 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /threads/{id}/sessions; failed heartbeats replay on that route
- GET /threads/{id}/sessions pages sessions on that thread (venue matches the thread)
- POST /threads/{id}/sessions/{id} and GET /threads/{id}/sessions/{id} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-thread-sessions-page-v1

Your job (#51):
1. Both clients POST /projects/{slug}/threads/{thread_id}/sessions/{session_id} to update a session on that project thread. Failed writes stay on the FIFO and replay on that same route (not POST /threads/{id}/sessions/{id} and not POST /sessions/{id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/threads/{thread_id}/sessions/{session_id} for one session on that thread. The thread must be on the project. The session venue must match the thread's last venue. Same require_user rules. 404 if the project is missing, the thread is not on the project, or the session is not on that thread. Still no public routes.
3. Both clients call GET /projects/{slug}/threads/{thread_id}/sessions/{session_id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-thread-session replay, project-thread-session GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-thread-session-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_50_TASK = """Sequenced #50 — next after junior-client-thread-session-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46, #47, #48, or #49).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #49 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /threads/{id}/sessions/{id}; failed updates replay on that route
- GET /threads/{id}/sessions/{id} loads one session on that thread (venue matches the thread)
- POST /sessions and GET /sessions already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-thread-session-get-v1

Your job (#50):
1. Both clients POST /threads/{id}/sessions to record a session on that thread. Failed writes stay on the FIFO and replay on that same route (not POST /sessions and not POST /threads/{id}/sessions/{id}). Same auth rule. No silent drop.
2. Add GET /threads/{id}/sessions to page sessions on that thread (limit/cursor or before_id). A session is on the thread when its venue matches the thread's last venue. Same require_user rules. 404 if the thread is missing. Still no public routes.
3. Both clients call GET /threads/{id}/sessions (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for thread-sessions replay, thread-sessions GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-thread-sessions-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_49_TASK = """Sequenced #49 — next after junior-client-project-thread-context-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46, #47, or #48).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #48 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/threads/{thread_id}/agent-context; failed pins replay on that route
- GET /projects/{slug}/threads/{thread_id}/agent-context loads one context pack on that thread
- POST /sessions/{id} and GET /sessions/{id} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-thread-context-get-v1

Your job (#49):
1. Both clients POST /threads/{id}/sessions/{id} to update a session on that thread. Failed writes stay on the FIFO and replay on that same route (not POST /sessions/{id}). Same auth rule. No silent drop.
2. Add GET /threads/{id}/sessions/{id} for one session on that thread. The session venue must match the thread's last venue. Same require_user rules. 404 if the thread is missing or the session is not on that thread. Still no public routes.
3. Both clients call GET /threads/{id}/sessions/{id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for thread-session replay, thread-session GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-thread-session-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_48_TASK = """Sequenced #48 — next after junior-client-project-thread-search-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, #46, or #47).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #47 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/threads/{thread_id}/search; failed searches replay on that route
- GET /projects/{slug}/threads/{thread_id}/search pages search hits on that thread
- POST /projects/{slug}/agent-context and GET /projects/{slug}/agent-context already exist
- POST /threads/{id}/agent-context/{slug} and GET /threads/{id}/agent-context/{slug} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-thread-search-page-v1

Your job (#48):
1. Both clients POST /projects/{slug}/threads/{thread_id}/agent-context to pin a context pack on that project thread. Failed writes stay on the FIFO and replay on that same route (not POST /projects/{slug}/agent-context and not POST /threads/{id}/agent-context/{slug}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/threads/{thread_id}/agent-context for one context pack on that thread. The thread must be on the project. Same require_user rules. 404 if the project is missing or the thread is not on the project. Still no public routes.
3. Both clients call GET /projects/{slug}/threads/{thread_id}/agent-context (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-thread-context replay, project-thread-context GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-thread-context-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_47_TASK = """Sequenced #47 — next after junior-client-project-thread-search-hit-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, #45, or #46).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #46 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/threads/{thread_id}/search/{message_id}; failed updates replay on that route
- GET /projects/{slug}/threads/{thread_id}/search/{message_id} loads one search hit on that thread
- POST /threads/{id}/search and GET /threads/{id}/search already exist
- POST /projects/{slug}/search and GET /projects/{slug}/search already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-thread-search-hit-get-v1

Your job (#47):
1. Both clients POST /projects/{slug}/threads/{thread_id}/search to run a search on that project thread. Failed writes stay on the FIFO and replay on that same route (not GET /search, not POST /threads/{id}/search, not POST /projects/{slug}/search, and not POST /projects/{slug}/threads/{thread_id}/search/{message_id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/threads/{thread_id}/search to page search hits on that thread (q plus limit/cursor or before_id). The thread must be on the project. Same require_user rules. 404 if the project is missing or the thread is not on the project. Still no public routes.
3. Both clients call GET /projects/{slug}/threads/{thread_id}/search (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-thread-search replay, project-thread-search GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-thread-search-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_46_TASK = """Sequenced #46 — next after junior-client-project-thread-agents-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, #44, or #45).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #45 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/threads/{thread_id}/agents; failed launches replay on that route
- GET /projects/{slug}/threads/{thread_id}/agents pages agent runs on that thread
- GET /threads/{id}/search/{id} and POST /threads/{id}/search/{id} already exist
- GET /projects/{slug}/search/{id} and POST /projects/{slug}/search/{id} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-thread-agents-page-v1

Your job (#46):
1. Both clients POST /projects/{slug}/threads/{thread_id}/search/{message_id} to update a search hit on that project thread. Failed writes stay on the FIFO and replay on that same route (not POST /projects/{slug}/search/{id} and not POST /threads/{id}/search/{id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/threads/{thread_id}/search/{message_id} for one search hit on that thread. The thread must be on the project. Same require_user rules. 404 if the project is missing, the thread is not on the project, or the hit is not on that thread. Still no public routes.
3. Both clients call GET /projects/{slug}/threads/{thread_id}/search/{message_id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-thread search-hit replay, project-thread search-hit GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-thread-search-hit-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_45_TASK = """Sequenced #45 — next after junior-client-project-thread-agent-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, #43, or #44).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #44 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/threads/{thread_id}/agents/{run_id}; failed updates replay on that route
- GET /projects/{slug}/threads/{thread_id}/agents/{run_id} loads one agent run on that thread
- POST /projects/{slug}/agents and GET /projects/{slug}/agents already exist
- POST /threads/{id}/agents and GET /threads/{id}/agents already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-thread-agent-get-v1

Your job (#45):
1. Both clients POST /projects/{slug}/threads/{thread_id}/agents to record a launch on that project thread. Failed writes stay on the FIFO and replay on that same route (not POST /projects/{slug}/agents, not POST /threads/{id}/agents, and not POST /projects/{slug}/threads/{thread_id}/agents/{run_id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/threads/{thread_id}/agents to page agent runs on that thread (limit/cursor or before_id). The thread must be on the project. Same require_user rules. 404 if the project is missing or the thread is not on the project. Still no public routes.
3. Both clients call GET /projects/{slug}/threads/{thread_id}/agents (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-thread-agent replay, project-thread-agents GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-thread-agents-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_44_TASK = """Sequenced #44 — next after junior-client-project-thread-memories-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, #42, or #43).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #43 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/threads/{thread_id}/memories; failed creates replay on that route
- GET /projects/{slug}/threads/{thread_id}/memories pages memories sourced from that thread
- GET /threads/{id}/agents/{id} and POST /threads/{id}/agents/{id} already exist
- GET /projects/{slug}/agents/{id} and POST /projects/{slug}/agents/{id} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-thread-memories-page-v1

Your job (#44):
1. Both clients POST /projects/{slug}/threads/{thread_id}/agents/{run_id} to update an agent run on that project thread. Failed writes stay on the FIFO and replay on that same route (not POST /projects/{slug}/agents/{id} and not POST /threads/{id}/agents/{id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/threads/{thread_id}/agents/{run_id} for one agent run on that thread. The thread must be on the project. Same require_user rules. 404 if the project is missing, the thread is not on the project, or the run is not on that thread. Still no public routes.
3. Both clients call GET /projects/{slug}/threads/{thread_id}/agents/{run_id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-thread-agent-update replay, project-thread-agent GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-thread-agent-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_43_TASK = """Sequenced #43 — next after junior-client-project-thread-memory-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, #41, or #42).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #42 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/threads/{thread_id}/memories/{memory_id}; failed updates replay on that route
- GET /projects/{slug}/threads/{thread_id}/memories/{memory_id} loads one memory sourced from that thread
- POST /projects/{slug}/memories and GET /projects/{slug}/memories already exist
- POST /threads/{id}/memories and GET /threads/{id}/memories already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-thread-memory-get-v1

Your job (#43):
1. Both clients POST /projects/{slug}/threads/{thread_id}/memories to save a memory on that project thread. Failed writes stay on the FIFO and replay on that same route (not POST /projects/{slug}/memories, not POST /threads/{id}/memories, and not POST /projects/{slug}/threads/{thread_id}/memories/{memory_id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/threads/{thread_id}/memories to page memories sourced from that thread (limit/cursor or before_id). The thread must be on the project. Same require_user rules. 404 if the project is missing or the thread is not on the project. Still no public routes.
3. Both clients call GET /projects/{slug}/threads/{thread_id}/memories (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-thread-memory replay, project-thread-memories GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-thread-memories-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_42_TASK = """Sequenced #42 — next after junior-client-project-thread-continue-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, #40, or #41).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #41 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/threads/{thread_id}/continue; failed resumes replay on that route
- GET /projects/{slug}/threads/{thread_id}/continue loads continue history for that project thread
- GET /threads/{id}/memories/{id} and POST /threads/{id}/memories/{id} already exist
- GET /projects/{slug}/memories/{id} and POST /projects/{slug}/memories/{id} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-thread-continue-get-v1

Your job (#42):
1. Both clients POST /projects/{slug}/threads/{thread_id}/memories/{memory_id} to update a memory on that project thread. Failed writes stay on the FIFO and replay on that same route (not POST /projects/{slug}/memories/{id} and not POST /threads/{id}/memories/{id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/threads/{thread_id}/memories/{memory_id} for one memory sourced from that thread. The thread must be on the project. Same require_user rules. 404 if the project is missing, the thread is not on the project, or the memory is not on that thread. Still no public routes.
3. Both clients call GET /projects/{slug}/threads/{thread_id}/memories/{memory_id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-thread-memory-update replay, project-thread-memory GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-thread-memory-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_41_TASK = """Sequenced #41 — next after junior-client-project-thread-messages-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, #39, or #40).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #40 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/threads/{thread_id}/messages; failed creates replay on that route
- GET /projects/{slug}/threads/{thread_id}/messages pages messages on that thread
- POST /projects/{slug}/continue and GET /projects/{slug}/continue already exist
- POST /threads/{id}/continue and GET /threads/{id}/continue already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-thread-messages-page-v1

Your job (#41):
1. Both clients POST /projects/{slug}/threads/{thread_id}/continue to resume that project thread. Failed writes stay on the FIFO and replay on that same route (not POST /projects/{slug}/continue, not POST /threads/{id}/continue, and not POST /projects/{slug}/threads/{thread_id}/messages). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/threads/{thread_id}/continue for continue history on that thread (limit/cursor or before_id). The thread must be on the project. Same require_user rules. 404 if the project is missing or the thread is not on the project. Still no public routes.
3. Both clients call GET /projects/{slug}/threads/{thread_id}/continue (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-thread-continue replay, project-thread-continue GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-thread-continue-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_40_TASK = """Sequenced #40 — next after junior-client-project-thread-message-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, #38, or #39).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #39 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/threads/{thread_id}/messages/{message_id}; failed updates replay on that route
- GET /projects/{slug}/threads/{thread_id}/messages/{message_id} loads one message on that thread
- POST /projects/{slug}/messages and GET /projects/{slug}/messages already exist
- POST /threads/{id}/messages and GET /threads/{id}/messages already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-thread-message-get-v1

Your job (#40):
1. Both clients POST /projects/{slug}/threads/{thread_id}/messages to save a message on that project thread. Failed writes stay on the FIFO and replay on that same route (not POST /projects/{slug}/messages, not POST /threads/{id}/messages, and not POST /projects/{slug}/threads/{thread_id}/messages/{message_id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/threads/{thread_id}/messages to page messages on that thread (limit/cursor or before_id). The thread must be on the project. Same require_user rules. 404 if the project is missing or the thread is not on the project. Still no public routes.
3. Both clients call GET /projects/{slug}/threads/{thread_id}/messages (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-thread-message-create replay, project-thread-messages page GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-thread-messages-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_39_TASK = """Sequenced #39 — next after junior-client-project-threads-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, #37, or #38).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #38 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/threads; failed opens replay on that route
- GET /projects/{slug}/threads pages threads on that project
- GET /projects/{slug}/messages/{id} and POST /threads/{id}/messages/{id} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-threads-page-v1

Your job (#39):
1. Both clients POST /projects/{slug}/threads/{thread_id}/messages/{message_id} to update a message on that project thread. Failed writes stay on the FIFO and replay on that same route (not POST /projects/{slug}/messages/{id} and not POST /threads/{id}/messages/{id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/threads/{thread_id}/messages/{message_id} for one message on that thread. The thread must be on the project. Same require_user rules. 404 if the project is missing, the thread is not on the project, or the message is not on that thread. Still no public routes.
3. Both clients call GET /projects/{slug}/threads/{thread_id}/messages/{message_id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-thread-message-update replay, project-thread-message GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-thread-message-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_38_TASK = """Sequenced #38 — next after junior-client-project-thread-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, #36, or #37).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #37 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/threads/{id}; failed updates replay on that route
- GET /projects/{slug}/threads/{id} loads one thread on that project
- POST /threads and GET /threads already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-thread-get-v1

Your job (#38):
1. Both clients POST /projects/{slug}/threads to open a thread on that project. Failed writes stay on the FIFO and replay on that same route (not POST /threads and not POST /projects/{slug}/threads/{id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/threads to page threads on that project (limit/cursor or before_id). Threads are the pinned context thread, threads tied to an agent run for that slug, and threads opened on that project. Same require_user rules. 404 if the project is missing. Still no public routes.
3. Both clients call GET /projects/{slug}/threads (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-thread-create replay, project-threads page GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-threads-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_37_TASK = """Sequenced #37 — next after junior-client-project-continue-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, #35, or #36).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #36 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/continue; failed resumes replay on that route
- GET /projects/{slug}/continue loads continue history for that project's pinned thread
- POST /threads/{id} and GET /threads/{id} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-continue-get-v1

Your job (#37):
1. Both clients POST /projects/{slug}/threads/{id} to update a thread on that project. Failed writes stay on the FIFO and replay on that same route (not POST /threads/{id} and not POST /projects/{slug}/continue). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/threads/{id} for one thread on that project. A thread is on the project when it is the pinned context thread or tied to an agent run for that slug. Same require_user rules. 404 if the project is missing or the thread is not on that project. Still no public routes.
3. Both clients call GET /projects/{slug}/threads/{id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-thread-update replay, project-thread GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-thread-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_36_TASK = """Sequenced #36 — next after junior-client-project-messages-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, #34, or #35).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #35 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/messages; failed creates replay on that route
- GET /projects/{slug}/messages pages messages on that project
- GET /threads/{id}/continue and POST /threads/{id}/continue already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-messages-page-v1

Your job (#36):
1. Both clients POST /projects/{slug}/continue to resume that project's pinned thread. Failed writes stay on the FIFO and replay on that same route (not POST /threads/{id}/continue and not POST /projects/{slug}/messages). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/continue for continue history on that pinned thread (limit/cursor or before_id). Same require_user rules. 404 if the project is missing or it has no thread. Still no public routes.
3. Both clients call GET /projects/{slug}/continue (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-continue replay, project-continue GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-continue-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_35_TASK = """Sequenced #35 — next after junior-client-project-message-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, #33, or #34).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #34 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/messages/{id}; failed updates replay on that route
- GET /projects/{slug}/messages/{id} loads one message on that project
- POST /threads/{id}/messages and GET /threads/{id}/messages already exist
- POST /messages and GET /messages already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-message-get-v1

Your job (#35):
1. Both clients POST /projects/{slug}/messages to save a message on that project. Failed writes stay on the FIFO and replay on that same route (not POST /messages and not POST /projects/{slug}/messages/{id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/messages to page messages on that project (limit/cursor or before_id). Messages are on the project's pinned thread and on threads with an agent run for that slug. Same require_user rules. 404 if the project is missing. Still no public routes.
3. Both clients call GET /projects/{slug}/messages (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-message-create replay, project-messages page GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-messages-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_34_TASK = """Sequenced #34 — next after junior-client-project-memories-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, #32, or #33).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #33 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/memories; failed creates replay on that route
- GET /projects/{slug}/memories pages memories on that project
- POST /threads/{id}/messages/{id} and GET /threads/{id}/messages/{id} already exist
- POST /messages/{id} and GET /messages/{id} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-memories-page-v1

Your job (#34):
1. Both clients POST /projects/{slug}/messages/{id} to update a message on that project. Failed writes stay on the FIFO and replay on that same route (not POST /messages/{id} and not POST /threads/{id}/messages/{id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/messages/{id} for one message on that project. Same require_user rules. 404 if the project is missing or the message is not on that project. Still no public routes.
3. Both clients call GET /projects/{slug}/messages/{id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-message-update replay, project-message GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-message-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_33_TASK = """Sequenced #33 — next after junior-client-project-memory-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, #31, or #32).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #32 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/memories/{id}; failed updates replay on that route
- GET /projects/{slug}/memories/{id} loads one memory on that project
- POST /threads/{id}/memories and GET /threads/{id}/memories already exist
- POST /memories and GET /memories already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-memory-get-v1

Your job (#33):
1. Both clients POST /projects/{slug}/memories to save a memory on that project. Failed writes stay on the FIFO and replay on that same route (not POST /memories and not POST /projects/{slug}/memories/{id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/memories to page memories on that project (limit/cursor or before_id). Memories are facts whose source thread is pinned to that project or tied to an agent run for that slug. Same require_user rules. 404 if the project is missing. Still no public routes.
3. Both clients call GET /projects/{slug}/memories (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-memory-create replay, project-memories page GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-memories-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_32_TASK = """Sequenced #32 — next after junior-client-project-context-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, #30, or #31).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #31 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/agent-context; failed pins replay on that route
- GET /projects/{slug}/agent-context loads one context pack on that project
- POST /threads/{id}/memories/{id} and GET /threads/{id}/memories/{id} already exist
- POST /memories/{id} and GET /memories/{id} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-context-get-v1

Your job (#32):
1. Both clients POST /projects/{slug}/memories/{id} to update a memory on that project. Failed writes stay on the FIFO and replay on that same route (not POST /memories/{id} and not POST /threads/{id}/memories/{id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/memories/{id} for one memory on that project. Same require_user rules. 404 if the project is missing or the memory is not on that project. Still no public routes.
3. Both clients call GET /projects/{slug}/memories/{id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-memory-update replay, project-memory GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-memory-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_31_TASK = """Sequenced #31 — next after junior-client-project-search-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, #29, or #30).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #30 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/search/{id}; failed updates replay on that route
- GET /projects/{slug}/search/{id} loads one search hit on that project
- POST /threads/{id}/agent-context/{slug} and GET /threads/{id}/agent-context/{slug} already exist
- POST /agent-context/{slug} and GET /agent-context/{slug} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-search-get-v1

Your job (#31):
1. Both clients POST /projects/{slug}/agent-context to pin a context pack on that project. Failed writes stay on the FIFO and replay on that same route (not POST /agent-context/{slug} and not POST /threads/{id}/agent-context/{slug}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/agent-context for one context pack on that project. Same require_user rules. 404 if the project is missing. Still no public routes.
3. Both clients call GET /projects/{slug}/agent-context (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-context-update replay, project-context GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-context-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_30_TASK = """Sequenced #30 — next after junior-client-thread-context-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, #28, or #29).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #29 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/search; failed searches replay on that route
- GET /projects/{slug}/search pages search hits on that project
- POST /threads/{id}/agent-context/{slug} and GET /threads/{id}/agent-context/{slug} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-thread-context-get-v1

Your job (#30):
1. Both clients POST /projects/{slug}/search/{id} to update a search hit on that project. Failed writes stay on the FIFO and replay on that same route (not POST /search/{id} and not POST /threads/{id}/search/{id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/search/{id} for one search hit on that project. Same require_user rules. 404 if the project is missing or the hit is not on that project. Still no public routes.
3. Both clients call GET /projects/{slug}/search/{id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-search-update replay, project-search GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-search-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_29_TASK = """Sequenced #29 — next after junior-client-thread-search-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, #27, or #28).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #28 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /threads/{id}/search; failed searches replay on that route
- GET /threads/{id}/search pages search hits on that thread
- POST /agent-context/{slug} and GET /agent-context/{slug} already exist
- POST /threads/{id}/search/{id} and GET /threads/{id}/search/{id} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-thread-search-page-v1

Your job (#29):
1. Both clients POST /projects/{slug}/search to run a search on that project. Failed writes stay on the FIFO and replay on that same route (not GET /search, not POST /threads/{id}/search, and not POST /search/{id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/search to page search hits on that project (q plus limit/cursor or before_id). Hits are messages on the project's pinned thread and on threads with an agent run for that slug. Same require_user rules. 404 if the project is missing. Still no public routes.
3. Both clients POST /threads/{id}/agent-context/{slug} to pin a context pack on that thread. Failed writes stay on the FIFO and replay on that same route (not POST /agent-context/{slug}). Same auth rule. No silent drop.
4. Add GET /threads/{id}/agent-context/{slug} for one context pack on that thread and project. Same require_user rules. 404 if the thread is missing or the project is missing. Still no public routes.
5. Keep SQL idempotent; no DROP TABLE. No new public routes.
6. Extend smoke tests for project-search replay, thread-context GET, and 403. Keep existing tests green.
7. Health stamp: junior-client-thread-context-get-v1 (project search from this same step is junior-client-project-search-page-v1).
8. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_28_TASK = """Sequenced #28 — next after junior-client-thread-search-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, #26, or #27).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #27 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /threads/{id}/search/{id}; failed updates replay on that route
- GET /threads/{id}/search/{id} loads one search hit on that thread
- POST /threads/{id}/agents and GET /threads/{id}/agents already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-thread-search-get-v1

Your job (#28):
1. Both clients POST /threads/{id}/search to run a search on that thread. Failed writes stay on the FIFO and replay on that same route (not GET /search and not POST /search/{id}). Same auth rule. No silent drop.
2. Add GET /threads/{id}/search to page search hits on that thread (q plus limit/cursor or before_id). Same require_user rules. 404 if the thread is missing. Still no public routes.
3. Both clients call GET /threads/{id}/search (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for thread-search replay, thread-search page GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-thread-search-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_27_TASK = """Sequenced #27 — next after junior-client-thread-agents-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, #25, or #26).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #26 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /threads/{id}/agents; failed launches replay on that route
- GET /threads/{id}/agents pages agent runs on that thread
- POST /threads/{id}/agents/{id} and GET /threads/{id}/agents/{id} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-thread-agents-page-v1

Your job (#27):
1. Both clients POST /threads/{id}/search/{id} to update a search hit on that thread. Failed writes stay on the FIFO and replay on that same route (not POST /search/{id}). Same auth rule. No silent drop.
2. Add GET /threads/{id}/search/{id} for one search hit on that thread. Same require_user rules. 404 if the thread is missing or the hit is not on that thread. Still no public routes.
3. Both clients call GET /threads/{id}/search/{id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for thread-search-update replay, thread-search GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-thread-search-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_26_TASK = """Sequenced #26 — next after junior-client-thread-agent-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, #24, or #25).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #25 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /threads/{id}/agents/{id}; failed updates replay on that route
- GET /threads/{id}/agents/{id} loads one agent run on that thread
- POST /projects/{slug}/agents and GET /projects/{slug}/agents already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-thread-agent-get-v1

Your job (#26):
1. Both clients POST /threads/{id}/agents to record an agent launch on that thread. Failed writes stay on the FIFO and replay on that same route (not POST /agents and not POST /projects/{slug}/agents). Same auth rule. No silent drop.
2. Add GET /threads/{id}/agents to page agent runs on that thread (limit/cursor or before_id). Same require_user rules. 404 if the thread is missing. Still no public routes.
3. Both clients call GET /threads/{id}/agents (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for thread-agent-launch replay, thread-agents page GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-thread-agents-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_25_TASK = """Sequenced #25 — next after junior-client-thread-memories-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, #23, or #24).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #24 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /threads/{id}/memories; failed creates replay on that route
- GET /threads/{id}/memories pages memories on that thread
- POST /projects/{slug}/agents and GET /projects/{slug}/agents already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-thread-memories-page-v1

Your job (#25):
1. Both clients POST /threads/{id}/agents/{id} to update an agent run on that thread. Failed writes stay on the FIFO and replay on that same route (not POST /agents/{id} and not POST /projects/{slug}/agents/{id}). Same auth rule. No silent drop.
2. Add GET /threads/{id}/agents/{id} for one agent run on that thread. Same require_user rules. 404 if the thread is missing or the run is not on that thread. Still no public routes.
3. Both clients call GET /threads/{id}/agents/{id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for thread-agent-update replay, thread-agent GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-thread-agent-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_24_TASK = """Sequenced #24 — next after junior-client-project-agents-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22, or #23).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #23 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/agents; failed launches replay on that route
- GET /projects/{slug}/agents pages agent runs on that project
- POST /threads/{id}/memories/{id} and GET /threads/{id}/memories/{id} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-agents-page-v1

Your job (#24):
1. Both clients POST /threads/{id}/memories to save a memory on that thread. Failed writes stay on the FIFO and replay on that same route (not POST /memories and not POST /threads/{id}/memories/{id}). Same auth rule. No silent drop.
2. Add GET /threads/{id}/memories to page memories on that thread (limit/cursor or before_id). Same require_user rules. 404 if the thread is missing. Still no public routes.
3. Both clients call GET /threads/{id}/memories (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for thread-memory-create replay, thread-memories page GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-thread-memories-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_23_TASK = """Sequenced #23 — next after junior-client-thread-memory-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, or #22).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #22 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /threads/{id}/memories/{id}; failed updates replay on that route
- GET /threads/{id}/memories/{id} loads one memory on that thread
- POST /projects/{slug}/agents/{id} and GET /projects/{slug}/agents/{id} already exist
- require_user; demo 403; no new public routes
- Health stamp junior-client-thread-memory-get-v1

Your job (#23):
1. Both clients POST /projects/{slug}/agents to record an agent launch on that project. Failed writes stay on the FIFO and replay on that same route (not POST /agents). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/agents to page agent runs on that project (limit/cursor or before_id). Same require_user rules. 404 if the project is missing. Still no public routes.
3. Both clients call GET /projects/{slug}/agents (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-agent-launch replay, project-agents page GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-agents-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_22_TASK = """Sequenced #22 — next after junior-client-project-agent-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, #20, or #21).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #21 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}/agents/{id}; failed updates replay on that route
- GET /projects/{slug}/agents/{id} loads one agent run on that project
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-agent-get-v1

Your job (#22):
1. Both clients POST /threads/{id}/memories/{id} to update a memory on that thread. Failed writes stay on the FIFO and replay on that same route (not POST /memories/{id}). Same auth rule. No silent drop.
2. Add GET /threads/{id}/memories/{id} for one memory on that thread. Same require_user rules. Still no public routes.
3. Both clients call GET /threads/{id}/memories/{id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for thread-memory-update replay, thread-memory GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-thread-memory-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_21_TASK = """Sequenced #21 — next after junior-client-continue-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, #19, or #20).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 through #20 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /threads/{id}/messages/{id}; failed updates replay on that route
- GET /threads/{id}/continue loads one continue history pack
- require_user; demo 403; no new public routes
- Health stamp junior-client-continue-get-v1

Your job (#21):
1. Both clients POST /projects/{slug}/agents/{id} to update an agent run on that project. Failed writes stay on the FIFO and replay on that same route (not POST /agents/{id}). Same auth rule. No silent drop.
2. Add GET /projects/{slug}/agents/{id} for one agent run on that project. Same require_user rules. Still no public routes.
3. Both clients call GET /projects/{slug}/agents/{id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-agent-update replay, project-agent GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-agent-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_20_TASK = """Sequenced #20 — next after junior-client-thread-message-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, or #19).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #18, and #19 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /agent-context/{slug}; failed updates replay on that route
- GET /threads/{id}/messages/{id} loads one thread message
- POST /threads, /threads/{id}, /sessions, /sessions/{id}, /memories, /messages/{id}, /projects, /agents, /search/{id}, and continue history already page and replay
- require_user; demo 403; no new public routes
- Health stamp junior-client-thread-message-get-v1

Your job (#20):
1. Both clients POST /threads/{id}/messages/{id} to update an existing thread message. Failed writes stay on the FIFO and replay on that same route (not POST /messages/{id} and not POST /threads/{id}/messages). Same auth rule. No silent drop.
2. Add GET /threads/{id}/continue for one continue history pack. Same require_user rules. Still no public routes.
3. Both clients call GET /threads/{id}/continue (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for thread-message-update replay, continue GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-continue-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_19_TASK = """Sequenced #19 — next after junior-client-context-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, or #18).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, and #18 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /search/{id}; failed updates replay on that route
- GET /agent-context/{slug} loads one project context pack
- POST /threads, /threads/{id}, /sessions, /sessions/{id}, /memories, /messages/{id}, /projects, /agents, and continue history already page and replay
- require_user; demo 403; no new public routes
- Health stamp junior-client-context-get-v1

Your job (#19):
1. Both clients POST /agent-context/{slug} to pin query/thread on that project pack. Failed writes stay on the FIFO and replay on that same route (not GET /agent-context). Same auth rule. No silent drop.
2. Add GET /threads/{id}/messages/{id} for one thread message. Same require_user rules. Still no public routes.
3. Both clients call GET /threads/{id}/messages/{id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for context-update replay, nested-message GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-thread-message-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_18_TASK = """Sequenced #18 — next after junior-client-search-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, or #17).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7, #8, #9, #10, #11, #12, #13, #14, #15, #16, and #17 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /agents/{id}; failed updates replay on that route
- GET /search/{id} loads one owner search hit
- POST /threads, /threads/{id}, /sessions, /sessions/{id}, /memories, /messages/{id}, /projects, /agents, and continue history already page and replay
- require_user; demo 403; no new public routes
- Health stamp junior-client-search-get-v1

Your job (#18):
1. Both clients POST /search/{id} to update an existing search hit. Failed writes stay on the FIFO and replay on that same route (not GET /search). Same auth rule. No silent drop.
2. Add GET /agent-context/{slug} for one project context pack. Same require_user rules. Still no public routes.
3. Both clients call GET /agent-context/{slug} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for search-hit-update replay, single-context GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-context-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_17_TASK = """Sequenced #17 — next after junior-client-project-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, #15, or #16).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7, #8, #9, #10, #11, #12, #13, #14, #15, and #16 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /messages/{id}; failed updates replay on that route
- GET /projects/{slug} loads one owner project
- POST /threads, /threads/{id}, /sessions, /sessions/{id}, /memories, /projects, /agents, and continue history already page and replay
- require_user; demo 403; no new public routes
- Health stamp junior-client-project-get-v1

Your job (#17):
1. Both clients POST /agents/{id} to update an existing agent run. Failed writes stay on the FIFO and replay on that same route (not POST /agents). Same auth rule. No silent drop.
2. Add GET /search/{id} for one search hit. Same require_user rules. Still no public routes.
3. Both clients call GET /search/{id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for agent-update replay, single-search GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-search-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_16_TASK = """Sequenced #16 — next after junior-client-message-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, #14, or #15).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7, #8, #9, #10, #11, #12, #13, #14, and #15 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /sessions/{id}; failed updates replay on that route
- GET /messages/{id} loads one owner message
- POST /threads, /threads/{id}, /sessions, /memories, /projects, /agents, and continue history already page and replay
- require_user; demo 403; no new public routes
- Health stamp junior-client-message-get-v1

Your job (#16):
1. Both clients POST /messages/{id} to update an existing message. Failed writes stay on the FIFO and replay on that same route (not POST /messages). Same auth rule. No silent drop.
2. Add GET /projects/{slug} for one project. Same require_user rules. Still no public routes.
3. Both clients call GET /projects/{slug} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for message-update replay, single-project GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-project-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_15_TASK = """Sequenced #15 — next after junior-client-session-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, #13, or #14).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7, #8, #9, #10, #11, #12, #13, and #14 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /memories/{id}; failed updates replay on that route
- GET /sessions/{id} loads one owner session
- POST /threads, /threads/{id}, /sessions, /memories, /projects, /agents, and continue history already page and replay
- require_user; demo 403; no new public routes
- Health stamp junior-client-session-get-v1

Your job (#15):
1. Both clients POST /sessions/{id} to update an existing session. Failed writes stay on the FIFO and replay on that same route (not POST /sessions). Same auth rule. No silent drop.
2. Add GET /messages/{id} for one message. Same require_user rules. Still no public routes.
3. Both clients call GET /messages/{id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for session-update replay, single-message GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-message-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_14_TASK = """Sequenced #14 — next after junior-client-agent-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, #12, or #13).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7, #8, #9, #10, #11, #12, and #13 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /projects/{slug}; failed updates replay on that route
- GET /agents/{id} loads one owner agent run
- POST /threads, /threads/{id}, /sessions, /memories, /projects, /agents, and continue history already page and replay
- require_user; demo 403; no new public routes
- Health stamp junior-client-agent-get-v1 (later main also has junior-ubuntu-paste-v1)

Your job (#14):
1. Both clients POST /memories/{id} to update an existing memory. Failed writes stay on the FIFO and replay on that same route (not POST /memories). Same auth rule. No silent drop.
2. Add GET /sessions/{id} for one session. Same require_user rules. Still no public routes.
3. Both clients call GET /sessions/{id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for memory-update replay, single-session GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-session-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_13_TASK = """Sequenced #13 — next after junior-client-memory-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, #11, or #12).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7, #8, #9, #10, #11, and #12 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /threads; failed creates replay on that route
- GET /threads/{id} loads one owner thread
- POST /threads/{id} updates title/status and replays on that route
- GET /memories/{id} loads one owner memory
- POST /sessions, /memories, /projects, /agents, and continue history already page and replay
- require_user; demo 403; no new public routes
- Health stamp junior-client-memory-get-v1 (later main also has junior-merge-abort-v1)

Your job (#13):
1. Both clients POST /projects/{slug} to update an existing project. Failed writes stay on the FIFO and replay on that same route (not POST /projects). Same auth rule. No silent drop.
2. Add GET /agents/{id} for one agent run. Same require_user rules. Still no public routes.
3. Both clients call GET /agents/{id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project-update replay, single-agent GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-agent-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_12_TASK = """Sequenced #12 — next after junior-client-thread-get-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, #10, or #11).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7, #8, #9, #10, and #11 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /threads; failed creates replay on that route
- GET /threads/{id} loads one owner thread
- POST /sessions, /memories, /projects, /agents, and continue history already page and replay
- require_user; demo 403; no new public routes
- Health stamp junior-client-thread-get-v1

Your job (#12):
1. Both clients POST /threads/{id} to update title/status. Failed writes stay on the FIFO and replay on that same route. Same auth rule. No silent drop.
2. Add GET /memories/{id} for one memory. Same require_user rules. Still no public routes.
3. Both clients call GET /memories/{id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for thread-update replay, single-memory GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-memory-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_11_TASK = """Sequenced #11 — next after junior-client-sessions-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, #9, or #10).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7, #8, #9, and #10 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /sessions; failed heartbeats replay on that route
- GET /sessions pages with limit/cursor or before_id
- POST /memories, /projects, /agents, and continue history already page and replay
- require_user; demo 403; no new public routes
- Health stamp junior-client-sessions-page-v1

Your job (#11):
1. Both clients POST /threads (open). Failed writes stay on the FIFO and replay on that same route (not /messages). Same auth rule. No silent drop.
2. Add GET /threads/{id} for one thread. Same require_user rules. Still no public routes.
3. Both clients call GET /threads/{id} (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for thread-create replay, single-thread GET, and 403. Keep existing tests green.
6. Health stamp: junior-client-thread-get-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_10_TASK = """Sequenced #10 — next after junior-client-memory-write-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, #7, #8, or #9).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7, #8, and #9 are already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients POST /memories; failed writes replay on that route
- POST /threads/{id}/continue history pages with limit/cursor or before_id
- GET /projects, /agents, /search, /memories, /threads, /messages page the same way
- Clients POST /projects and /agents with FIFO replay
- require_user; demo 403; no new public routes
- Health stamp junior-client-memory-write-v1

Your job (#10):
1. Both clients POST /sessions (heartbeat). Failed writes stay on the FIFO and replay on that same route. Same auth rule. No silent drop.
2. Paginate GET /sessions (limit/cursor or before_id). Same require_user rules. Still no public routes.
3. Both clients call GET /sessions (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for session replay, session pagination, and 403. Keep existing tests green.
6. Health stamp: junior-client-sessions-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_9_TASK = """Sequenced #9 — next after junior-client-agents-page-v1 (do not redo #2, #3, #4, #5, #6, #7, or #8).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients keep a FIFO of failed posts and replay in order after the same login
- Shared GET /search and /memories take limit plus cursor or before_id
- Both clients POST /threads/{id}/continue for resume; failed continue posts stay on the queue
- require_user; demo 403; no new public routes
- Health stamp junior-client-queue-multi-v1
#7 and #8 live on their cursor/* branches (projects page, agent-context GET, POST /projects and /agents, GET /agents). Do not redo them.

Your job (#9):
1. Both clients POST /memories. Failed writes stay on the FIFO and replay on that same route. Same auth rule. No silent drop.
2. Paginate POST /threads/{id}/continue history (limit/cursor or before_id; X-Next-Cursor). Same require_user rules. Still no public routes.
3. Both clients pass those page params on continue. Failed continue posts stay on the queue.
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for memory replay, continue pagination, and 403. Keep existing tests green.
6. Health stamp: junior-client-memory-write-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_8_TASK = """Sequenced #8 — next after junior-client-context-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, or #7).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 is already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients replay queued continue posts through POST /threads/{id}/continue
- Shared GET /projects takes limit plus cursor or before_id
- Both clients call GET /projects and GET /agent-context
- require_user; demo 403; no new public routes
- Health stamp junior-client-context-page-v1

Your job (#8):
1. Both clients POST /projects and POST /agents. Failed writes stay on the FIFO and replay on those same routes. Same auth rule. No silent drop.
2. Paginate GET /agents (limit/cursor or before_id). Same require_user rules. Still no public routes.
3. Both clients call GET /agents (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for project/agent replay, agent-run pagination, and 403. Keep existing tests green.
6. Health stamp: junior-client-agents-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_7_TASK = """Sequenced #7 — next after junior-client-queue-multi-v1 on GitHub main (do not redo #2, #3, #4, #5, or #6).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #6 is already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients keep a FIFO of failed posts and replay in order after the same login
- Shared GET /search and /memories take limit plus cursor or before_id
- Both clients POST /threads/{id}/continue for resume; failed continue posts stay on the queue
- require_user; demo 403; no new public routes
- Health stamp junior-client-queue-multi-v1

Your job (#7):
1. Replay queued continue posts through POST /threads/{id}/continue (not /messages). Same auth rule. No silent drop.
2. Paginate GET /projects (limit/cursor or before_id). Same require_user rules. Still no public routes.
3. Both clients call GET /projects and GET /agent-context (same auth).
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for continue replay, project pagination, agent-context, and 403. Keep existing tests green.
6. Health stamp: junior-client-context-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_4_TASK = """Sequenced #4 — next after junior-shared-clients-v1 on production (do not redo #2 or #3).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done:
- Dockerfile copies backend/migrations → /app/migrations
- Boot applies 001 then 002; missing files fail init
- DATABASE_URL stays ${{Postgres.DATABASE_URL}}
- /api/v1/junior/* require_user; demo 403; no new public routes
- phone_client: venue phone, device junior-mobile, project junior-phone
- windows_client: venue windows, device windows-overlay, project windows-overlay
- Both post to /api/v1/junior/messages or /threads/{id}/messages
- Health reports junior-shared-clients-v1

Your job (#4):
1. Harden the two clients only: retries/backoff on 401/403/5xx, clear user-visible errors, no silent drop of posts.
2. Shared GET for threads/messages using the same auth rules; still no public routes.
3. Keep SQL idempotent; no DROP TABLE.
4. Extend smoke tests for retry/403 and GET paths. Keep existing tests green.
5. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_6_TASK = """Sequenced #6 — next after junior-client-queue-page-v1 on GitHub main (do not redo #2, #3, #4, or #5).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #5 is already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients persist last_failed_post and replay after the same login
- Shared GET /threads, /messages, and /threads/{id}/messages take limit plus cursor or before_id
- require_user; demo 403; no new public routes
- Health stamp junior-client-queue-page-v1

Your job (#6):
1. Local queue is a FIFO of failed posts (not only the last one). Replay in order after login. Same auth rule. No silent drop.
2. Paginate GET /search and GET /memories (limit/cursor or before_id). Same require_user rules. Still no public routes.
3. Both clients call POST /threads/{id}/continue for resume (same auth). Failed continue posts stay on the queue.
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for multi-item replay, search/memory pagination, continue, and 403. Keep existing tests green.
6. Health stamp: junior-client-queue-multi-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""


SEQ_5_TASK = """Sequenced #5 — next after junior-client-robustness-v1 on GitHub main (do not redo #2, #3, or #4).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main (739bafb or newer). #4 is already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Open a pull request into main so Bugbot reviews it automatically. Do not merge that pull request.

Already done on main:
- Phone and Windows clients retry 401/403/5xx with backoff
- Failed writes keep a user-visible error and last_failed_post
- Shared GET /api/v1/junior/threads, /messages, and /threads/{id}/messages
- require_user; demo 403; no new public routes
- Health stamp junior-client-robustness-v1

Your job (#5):
1. Persist last_failed_post across client restart (local queue, same auth, no silent drop). Replay after a successful login.
2. Surface the user-visible error in both clients (phone and windows overlay), not only in logs.
3. Paginate shared GET (limit/cursor or before_id). Same require_user rules. Still no public routes.
4. Keep SQL idempotent; no DROP TABLE. No new public routes.
5. Extend smoke tests for queue replay, pagination, and 403. Keep existing tests green.
6. Health stamp: junior-client-queue-page-v1
7. Commit on a cursor/* branch and push that branch only.

Return: branch name, commit SHA, files changed, Ubuntu merge commands for main.
"""

