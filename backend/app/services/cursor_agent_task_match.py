"""Matchers that pick a sequenced Cursor Cloud Agent prompt.

POLISH_2_TASK is the #2 polish prompt. _POLISH_2_RE matches messages that
request #2 polish. _NUM_WORDS, _SEQ_MENTION_RE, and _NEXT_STEP_RE parse a
sequence number or a next-step request. No imports beyond ``re``.
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
