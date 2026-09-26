from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.http_limits import redact_secrets
from app.services.demo_lock import is_locked

logger = logging.getLogger(__name__)

TIMEOUT_SEC = 45.0
START_TOOL_NAME = "cursor_start_agent"
CURSOR_TOOL_NAMES = frozenset({START_TOOL_NAME})

CURSOR_ON_APPEND = """
You can **start a real Cursor Cloud Agent** from chat (Steve's code twin — you spawn it; Cursor edits the repo in a cloud VM).
- **cursor_start_agent**: creates a Cloud Agent with prompt text, repo URL, and starting ref main on sb11b/Storykeep-.
- Cloud Agents commit on a **cursor/* branch**, not Steve's local main — the tool reply includes Ubuntu push steps and the agent URL.
- Use when Steve asks to start, launch, send, or go ahead — including “sequence number five”, “start next step”, or “go ahead and start”. A request to write a prompt stays a copy-paste block.
- The API key is already configured. Never say the key is missing, never say there is no agent start tool, and never ask Steve to define the sequence. Start it and return the agent URL.
- After the tool runs, give him the **agent URL** and the **Push to main (Ubuntu)** block from the tool data — do not bury instructions only in prose.
- Delegate turns auto-open a PR to main when the agent finishes unless he says otherwise.
- Tokens stay server-side; never echo CURSOR_API_KEY.
"""

CURSOR_OFF_APPEND = """
Cursor Cloud Agent start is wired but CURSOR_API_KEY is not set on the Storykeep Railway service yet.
Tell Steve to create a key in Cursor Dashboard → API Keys, then add CURSOR_API_KEY in Railway → storykeep → Variables — never paste keys into chat.
Until then, offer a copy-paste Cursor prompt block instead of claiming you started an agent.
"""

_START_RE = re.compile(
    r"\b(?:"
    r"start(?:\s+a)?\s+(?:cursor\s+)?(?:cloud\s+)?agent|"
    r"launch(?:\s+a)?\s+(?:cursor\s+)?(?:cloud\s+)?agent|"
    r"open(?:\s+a)?\s+(?:cursor\s+)?(?:cloud\s+)?agent|"
    r"spawn(?:\s+a)?\s+(?:cursor\s+)?(?:cloud\s+)?agent|"
    r"run(?:\s+this|\s+that|\s+it)?\s+in\s+(?:a\s+)?cursor\s+(?:cloud\s+)?agent|"
    r"delegate(?:\s+to)?\s+(?:a\s+)?cursor\s+(?:cloud\s+)?agent|"
    r"cursor\s+(?:cloud\s+)?agent\s+task|"
    r"send(?:\s+(?:a|the))?\s+(?:cursor\s+)?(?:cloud\s+)?agent"
    r")\b",
    re.I,
)
_SETUP_RE = re.compile(
    r"\b(?:CURSOR_API_KEY|cursor\s+(?:api\s+)?key|cursor\s+cloud\s+agent\s+key)\b",
    re.I,
)
_PROMPT_PREFIX_RES = (
    re.compile(
        r"^(?:please\s+)?(?:start|launch|open|spawn)\s+(?:a\s+)?(?:cursor\s+)?(?:cloud\s+)?agent\s*(?:to|:|—|-)\s*",
        re.I,
    ),
    re.compile(
        r"^(?:please\s+)?(?:start|launch|open|spawn)\s+(?:a\s+)?(?:cursor\s+)?(?:cloud\s+)?agent\s+",
        re.I,
    ),
    re.compile(
        r"^(?:please\s+)?run\s+(?:this|that|it)\s+in\s+(?:a\s+)?cursor\s+(?:cloud\s+)?agent\s*(?::|—|-)?\s*",
        re.I,
    ),
)
_BRANCH_EXPLICIT_RE = re.compile(
    r"\b(?:branch|ref|startingRef)\s+(?:named|called)?\s*([A-Za-z0-9._/-]+)\b",
    re.I,
)
_BRANCH_RE = re.compile(r"\b(?:on|from)\s+(?:branch\s+)?([A-Za-z0-9._/-]+)\b", re.I)
_BRANCH_SKIP = frozenset(
    {
        "a",
        "an",
        "the",
        "new",
        "feature",
        "separate",
        "fresh",
        "dedicated",
        "local",
        "remote",
        "its",
        "this",
        "that",
        "your",
        "my",
        "our",
        "to",
        "for",
        "in",
        "with",
        "and",
        "or",
        "storykeep",
        "storykeep-",
        "production",
        "repository",
        "repo",
        "github",
        "railway",
        "cursor",
        "junior",
        "chat",
        "pane",
        "project",
        "existing",
        "memory",
        "mobile",
    },
)
_NEGATED_START_RE = re.compile(
    r"(?:do\s+not|don't|dont|never|not)\s+$",
    re.I,
)
_AUTO_PR_RE = re.compile(
    r"\b(?:auto[\s-]?create\s+pr|open\s+a\s+pr|create\s+(?:a\s+)?pull\s+request)\b",
    re.I,
)

CURSOR_START_TOOL = {
    "type": "function",
    "function": {
        "name": START_TOOL_NAME,
        "description": (
            "Start a Cursor Cloud Agent on the Storykeep GitHub repo. "
            "Use when Steve explicitly asks to launch/start/open a Cursor or Cloud Agent task — "
            "not when he only wants a copy-paste prompt."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Full task instruction for the Cloud Agent (goal, files, done-when).",
                },
                "branch": {
                    "type": "string",
                    "description": "Git starting ref (branch or SHA). Default main.",
                    "default": "main",
                },
                "auto_create_pr": {
                    "type": "boolean",
                    "description": "Open a PR when the agent finishes.",
                    "default": False,
                },
            },
            "required": ["prompt"],
        },
    },
}

CURSOR_TOOLS = [CURSOR_START_TOOL]


@dataclass(frozen=True)
class CursorAgentOutcome:
    ok: bool
    text: str
    status_code: int = 200
    agent_id: str | None = None
    agent_url: str | None = None
    run_id: str | None = None


def _api_key() -> str:
    return (settings.cursor_api_key or "").strip()


def _repo_slug() -> str:
    override = (settings.cursor_agent_repo or "").strip().strip("/")
    if override:
        return override
    return (settings.github_repo or "sb11b/Storykeep-").strip().strip("/")


def _repo_url() -> str:
    slug = _repo_slug()
    if slug.startswith("http://") or slug.startswith("https://"):
        return slug.rstrip("/")
    return f"https://github.com/{slug}"


def _default_branch() -> str:
    return (settings.cursor_agent_branch or "main").strip() or "main"


def configured() -> bool:
    return bool(_api_key())


def owner_can_use(user: object | None) -> bool:
    return configured() and not is_locked(user)


def reject_demo(user: object) -> None:
    if is_locked(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cursor Cloud Agent is not enabled on this account",
        )


def wants_cursor_setup(message: str) -> bool:
    return bool(_SETUP_RE.search(message or ""))


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
}
_SEQ_MENTION_RE = re.compile(
    r"\bsequenc(?:e|ed)\s+(?:number\s+)?#?\s*"
    r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b"
    r"|\b(?:sequenced\s+)?#\s*(\d+)\b",
    re.I,
)
_NEXT_STEP_RE = re.compile(
    r"\b(?:send|start)(?:\s+the)?\s+next\s+step\b"
    r"|\bgo ahead and (?:send|start)\b"
    r"|\bmove on to the (?:next|nest) step\b"
    r"|\bsequenc(?:e|ed)\s+(?:number\s+)?#?\s*"
    r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b",
    re.I,
)

SEQ_4_TASK = """Sequenced #4 — next after junior-shared-clients-v1 on production (do not redo #2 or #3).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Do not open a pull request.

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


SEQ_8_TASK = """Sequenced #8 — next after junior-client-context-page-v1 on GitHub main (do not redo #2, #3, #4, #5, #6, or #7).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #7 is already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Do not open a pull request.

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

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #6 is already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Do not open a pull request.

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


SEQ_6_TASK = """Sequenced #6 — next after junior-client-queue-page-v1 on GitHub main (do not redo #2, #3, #4, or #5).

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main. #5 is already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Do not open a pull request.

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

Repo: github.com/sb11b/Storykeep- only. Branch from current GitHub main (739bafb or newer). #4 is already on main. Do not merge steve-bitsko Cursor PR #2. Do not change the owner email (angry.tune8751@fastmail.com). Do not git-push to main. Do not re-run SQL migrations. Do not open a pull request.

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


def _negated_at(text: str, start: int) -> bool:
    prefix = text[max(0, start - 64) : start]
    if _NEGATED_START_RE.search(prefix):
        return True
    return bool(re.search(r"\b(?:do\s+not|don't|dont|never)\b(?:\s+\w+){0,6}\s*$", prefix, re.I))


def _parse_seq_num(raw: str) -> int | None:
    token = (raw or "").strip().lower()
    if token.isdigit():
        return int(token)
    return _NUM_WORDS.get(token)


def sequence_number(message: str) -> int | None:
    text = message or ""
    for match in _SEQ_MENTION_RE.finditer(text):
        if _negated_at(text, match.start()):
            continue
        raw = next((group for group in match.groups() if group), "")
        number = _parse_seq_num(raw)
        if number is not None:
            return number
    return None


def _later_sequence_task(number: int, message: str) -> str:
    spoken = " ".join((message or "").split())
    return (
        f"Sequenced #{number} on GitHub main of sb11b/Storykeep- (StoryKeep). "
        "Steve asked to start this sequence. Do not refuse. Do not ask him to define it. "
        "Do not say there is no agent start tool. Do not redo #2, #3, #4, #5, #6, #7, or #8. "
        "Do not merge steve-bitsko Cursor PR #2. Do not change the owner email. "
        "Do not git-push to main. Do not re-run SQL. Do not open a pull request. "
        "Commit on a cursor/* branch and push that branch only.\n\n"
        f"His request: {spoken}"
    )


def next_step_task(message: str) -> str | None:
    text = message or ""
    number = sequence_number(text)
    if number == 4:
        return SEQ_4_TASK
    if number == 5:
        return SEQ_5_TASK
    if number == 6:
        return SEQ_6_TASK
    if number == 7:
        return SEQ_7_TASK
    if number == 8:
        return SEQ_8_TASK
    if number is not None and number > 8:
        return _later_sequence_task(number, text)
    if number == 2:
        return None
    for match in _NEXT_STEP_RE.finditer(text):
        if _negated_at(text, match.start()):
            continue
        return _later_sequence_task(9, text)
    return None


def sequenced_task(message: str) -> str | None:
    return polish_2_task(message) or next_step_task(message)


def wants_start(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if sequenced_task(text):
        return True
    if wants_cursor_setup(text):
        return True
    for match in _START_RE.finditer(text):
        prefix = text[max(0, match.start() - 32) : match.start()]
        if _NEGATED_START_RE.search(prefix):
            continue
        return True
    return False


def extract_prompt(message: str) -> str:
    text = (message or "").strip()
    if not text:
        return text
    for pattern in _PROMPT_PREFIX_RES:
        stripped = pattern.sub("", text).strip()
        if stripped and stripped != text:
            return stripped.lstrip(":—- ").strip()
    return text


def _valid_branch_ref(ref: str) -> bool:
    cleaned = (ref or "").strip().strip("/")
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if lowered in _BRANCH_SKIP:
        return False
    if len(cleaned) == 1 and not cleaned.isdigit():
        return False
    return True


def extract_branch(message: str) -> str:
    text = message or ""
    explicit = _BRANCH_EXPLICIT_RE.search(text)
    if explicit:
        ref = explicit.group(1).strip()
        if _valid_branch_ref(ref):
            return ref
    for match in _BRANCH_RE.finditer(text):
        ref = match.group(1).strip()
        if _valid_branch_ref(ref):
            return ref
    return _default_branch()


def wants_auto_create_pr(message: str) -> bool:
    return bool(_AUTO_PR_RE.search(message or ""))


def is_cursor_tool(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    fn = item.get("function") if isinstance(item.get("function"), dict) else {}
    name = str(fn.get("name") or item.get("name") or "").strip()
    return name in CURSOR_TOOL_NAMES


def _api_root() -> str:
    return (settings.cursor_api_url or "https://api.cursor.com").rstrip("/")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    key = _api_key()
    if not key:
        return 503, {"message": "Cursor API key not configured"}
    url = f"{_api_root()}{path}"
    try:
        with httpx.Client(timeout=TIMEOUT_SEC) as client:
            response = client.request(method, url, headers=_headers(), json=payload)
    except httpx.TimeoutException:
        return 504, {"message": "Cursor API timeout"}
    except httpx.HTTPError as exc:
        return 502, {"message": f"Cursor transport error: {exc}"}
    try:
        body = response.json()
    except json.JSONDecodeError:
        body = {"message": response.text[:500]}
    return response.status_code, body


def _post(path: str, payload: dict[str, Any]) -> tuple[int, Any]:
    return _request("POST", path, payload)


def _get(path: str) -> tuple[int, Any]:
    return _request("GET", path)


def _cursor_api_error_detail(body: Any) -> str:
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            message = str(err.get("message") or "").strip()
            if message:
                return message
        message = str(body.get("message") or "").strip()
        if message:
            return message
    return redact_secrets(str(body))[:400]


def push_workflow_for_user(
    *,
    agent_url: str | None,
    repo_slug: str | None = None,
    starting_branch: str = "main",
    auto_create_pr: bool = False,
) -> str:
    """Copy-paste Ubuntu steps — Cloud Agents use cursor/* branches, not local main."""
    slug = (repo_slug or _repo_slug()).strip().strip("/")
    repo_https = f"https://github.com/{slug}.git"
    agent_line = agent_url or "(agent URL from above)"
    pr_note = (
        "An open PR to main will be created when the agent finishes — merge it on GitHub, then deploy."
        if auto_create_pr
        else "On GitHub → Branches, find the new cursor/… branch the agent pushed."
    )
    return (
        "Push to main (Ubuntu) — Cloud Agents commit on cursor/*, not your local main:\n\n"
        f"Easiest: open {agent_line} → **Open in Cursor** → review → push (or merge the PR).\n\n"
        "Existing clone in Cursor terminal:\n"
        "```bash\n"
        "cd ~/Storykeep   # or your clone path\n"
        f"git remote add github {repo_https} 2>/dev/null || true\n"
        "git fetch github\n"
        "git branch -r | grep 'github/cursor/'   # note the branch name\n"
        f"git checkout {starting_branch}\n"
        f"git pull github {starting_branch}\n"
        "git merge github/cursor/YOUR-BRANCH-NAME\n"
        f"git push github {starting_branch}\n"
        "```\n"
        f"{pr_note}\n"
        "Then in Junior: Show GitHub status, then deploy Storykeep."
    )


def _format_agent_response(
    *,
    status_code: int,
    body: Any,
    prompt: str,
    branch: str,
    repo_url: str,
    auto_create_pr: bool = False,
) -> CursorAgentOutcome:
    if status_code >= 400:
        detail = _cursor_api_error_detail(body)
        return CursorAgentOutcome(
            False,
            f"Cursor Cloud Agent create failed (HTTP {status_code}): {detail}",
            status_code,
        )
    if not isinstance(body, dict):
        return CursorAgentOutcome(False, "Cursor API returned unexpected payload.", 502)
    agent = body.get("agent") if isinstance(body.get("agent"), dict) else {}
    run = body.get("run") if isinstance(body.get("run"), dict) else {}
    agent_id = str(agent.get("id") or "").strip() or None
    agent_url = str(agent.get("url") or "").strip() or None
    if agent_id and not agent_url:
        agent_url = f"https://cursor.com/agents/{quote(agent_id, safe='')}"
    name = str(agent.get("name") or "").strip()
    agent_status = str(agent.get("status") or "unknown")
    run_status = str(run.get("status") or "unknown")
    lines = [
        "Cursor Cloud Agent started server-side this turn:",
        f"- Repo: {repo_url}",
        f"- Branch: {branch}",
        f"- Prompt: {' '.join(prompt.split())[:240]}{'…' if len(prompt) > 240 else ''}",
    ]
    if name:
        lines.append(f"- Name: {name}")
    if agent_id:
        lines.append(f"- Agent id: {agent_id}")
    if agent_url:
        lines.append(f"- Agent URL: {agent_url}")
    lines.append(f"- Agent status: {agent_status}")
    if run.get("id"):
        lines.append(f"- Run id: {run.get('id')}")
    lines.append(f"- Run status: {run_status}")
    if auto_create_pr:
        lines.append("- Auto PR: enabled (merge to main on GitHub when the agent finishes)")
    lines.append(
        "Cloud Agents push to a cursor/* branch — not Steve's local main checkout. "
        "Include the Push to main block below in your reply."
    )
    lines.append("")
    lines.append(
        push_workflow_for_user(
            agent_url=agent_url,
            starting_branch=branch,
            auto_create_pr=auto_create_pr,
        )
    )
    lines.append(
        "Report the Agent URL and the Push to main (Ubuntu) block to Steve. "
        "Do not say the tool might be unavailable — this block is authoritative for this turn."
    )
    run_id = str(run.get("id") or "").strip() or None
    return CursorAgentOutcome(True, "\n".join(lines), status_code, agent_id, agent_url, run_id)


def start_agent(
    prompt: str,
    *,
    branch: str | None = None,
    auto_create_pr: bool | None = None,
    source_message: str | None = None,
) -> CursorAgentOutcome:
    if not configured():
        return CursorAgentOutcome(False, CURSOR_OFF_APPEND.strip(), 503)
    task = (prompt or "").strip()
    if not task and source_message:
        task = extract_prompt(source_message)
    if not task:
        return CursorAgentOutcome(False, "A non-empty prompt is required to start a Cloud Agent.", 400)
    ref = (branch or extract_branch(source_message or "") if source_message else None) or _default_branch()
    ref = ref.strip() or _default_branch()
    repo_url = _repo_url()
    auto_pr = auto_create_pr
    if auto_pr is None and source_message:
        auto_pr = wants_auto_create_pr(source_message)
    payload: dict[str, Any] = {
        "prompt": {"text": task},
        "repos": [{"url": repo_url, "startingRef": ref}],
    }
    if auto_pr:
        payload["autoCreatePR"] = True
    status_code, body = _post("/v1/agents", payload)
    return _format_agent_response(
        status_code=status_code,
        body=body,
        prompt=task,
        branch=ref,
        repo_url=repo_url,
        auto_create_pr=bool(auto_pr),
    )


def format_start_for_model(outcome: CursorAgentOutcome) -> str:
    prefix = "Live Cursor Cloud Agent data for this turn:"
    return f"{prefix}\n{outcome.text}"


def summarize_agent_for_user(outcome: CursorAgentOutcome) -> str:
    """Plain reply when xAI stays silent after server-side agent start."""
    if outcome.ok and outcome.agent_url:
        bits = [
            "Cursor Cloud Agent started.",
            f"Open: {outcome.agent_url}",
            "Commits land on a cursor/* branch — use Open in Cursor or the Ubuntu merge steps below.",
            "When it finishes, this chat gets the branch name, what changed, and the merge commands.",
        ]
        workflow = push_workflow_for_user(agent_url=outcome.agent_url)
        return f"{bits[0]} {bits[1]}\n\n{bits[2]}\n\n{bits[3]}\n\n{workflow}"
    text = (outcome.text or "").strip()
    if not outcome.ok and text:
        if text.startswith("Cursor Cloud Agent create failed"):
            return text
        return f"Could not start Cursor Cloud Agent: {text.splitlines()[0][:400]}"
    if text:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- Agent URL:"):
                url = stripped.split(":", 1)[1].strip()
                return f"Cursor Cloud Agent started. Open: {url}"
        return text.splitlines()[0][:500]
    if outcome.ok:
        return "Cursor Cloud Agent started — open Cursor → Agents to watch progress."
    return "Could not start Cursor Cloud Agent — check server logs or CURSOR_API_KEY on Railway."


def _parse_tool_args(arguments: str) -> dict[str, Any]:
    try:
        parsed = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def assemble_tool_calls(fragments: list[dict] | None) -> list[dict[str, Any]]:
    buckets: dict[int, dict[str, str]] = {}
    for item in fragments or []:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index") or 0)
        except (TypeError, ValueError):
            index = 0
        slot = buckets.setdefault(index, {"name": "", "arguments": ""})
        fn = item.get("function") if isinstance(item.get("function"), dict) else {}
        name = fn.get("name") or item.get("name")
        if isinstance(name, str) and name:
            slot["name"] = name
        args = fn.get("arguments") if isinstance(fn, dict) else item.get("arguments")
        if isinstance(args, str):
            slot["arguments"] += args
    calls: list[dict[str, Any]] = []
    for slot in buckets.values():
        name = slot.get("name") or ""
        if name not in CURSOR_TOOL_NAMES:
            continue
        calls.append({"name": name, **_parse_tool_args(slot.get("arguments") or "")})
    return calls


def assemble_tool_call(fragments: list[dict] | None) -> dict[str, Any] | None:
    calls = assemble_tool_calls(fragments)
    return calls[0] if calls else None


TERMINAL_RUN_STATUSES = frozenset({"FINISHED", "ERROR", "CANCELLED", "EXPIRED", "FAILED"})


@dataclass(frozen=True)
class AgentRunSnapshot:
    status: str
    result: str = ""
    branch: str | None = None
    pr_url: str | None = None
    run_id: str | None = None
    reachable: bool = True


def _branch_from_run(body: dict[str, Any]) -> tuple[str | None, str | None]:
    git = body.get("git") if isinstance(body.get("git"), dict) else {}
    branches = git.get("branches") if isinstance(git.get("branches"), list) else []
    for item in branches:
        if not isinstance(item, dict):
            continue
        branch = str(item.get("branch") or "").strip()
        pr_url = str(item.get("prUrl") or "").strip() or None
        if branch or pr_url:
            return branch or None, pr_url
    target = body.get("target") if isinstance(body.get("target"), dict) else {}
    branch = str(target.get("branchName") or "").strip() or None
    pr_url = str(target.get("prUrl") or "").strip() or None
    return branch, pr_url


def _snapshot_from_run(body: dict[str, Any], *, run_id: str | None) -> AgentRunSnapshot:
    status_name = str(body.get("status") or "UNKNOWN").strip().upper() or "UNKNOWN"
    result = str(body.get("result") or body.get("summary") or "").strip()
    branch, pr_url = _branch_from_run(body)
    found_run = str(body.get("id") or run_id or "").strip() or None
    return AgentRunSnapshot(status_name, result, branch, pr_url, found_run, True)


def fetch_run(agent_id: str, run_id: str | None = None) -> AgentRunSnapshot:
    """Read the current Cloud Agent run. Unreachable snapshots stay pending."""
    agent = (agent_id or "").strip()
    if not agent:
        return AgentRunSnapshot("UNKNOWN", reachable=False)
    current_run = (run_id or "").strip() or None
    if not current_run:
        status_code, body = _get(f"/v1/agents/{quote(agent, safe='')}")
        if status_code == 404:
            return AgentRunSnapshot("MISSING", reachable=True)
        if status_code >= 400 or not isinstance(body, dict):
            return AgentRunSnapshot("UNKNOWN", reachable=False)
        current_run = str(body.get("latestRunId") or "").strip() or None
        nested = body.get("run") if isinstance(body.get("run"), dict) else {}
        if not current_run:
            current_run = str(nested.get("id") or "").strip() or None
        if not current_run:
            return AgentRunSnapshot(str(body.get("status") or "UNKNOWN").upper(), run_id=None, reachable=True)
    status_code, body = _get(f"/v1/agents/{quote(agent, safe='')}/runs/{quote(current_run, safe='')}")
    if status_code == 404:
        return AgentRunSnapshot("MISSING", run_id=current_run, reachable=True)
    if status_code >= 400 or not isinstance(body, dict):
        return AgentRunSnapshot("UNKNOWN", run_id=current_run, reachable=False)
    run_body = body.get("run") if isinstance(body.get("run"), dict) else body
    if not isinstance(run_body, dict):
        return AgentRunSnapshot("UNKNOWN", run_id=current_run, reachable=False)
    return _snapshot_from_run(run_body, run_id=current_run)


def merge_commands(branch: str, *, starting_branch: str = "main", repo_slug: str | None = None) -> str:
    slug = (repo_slug or _repo_slug()).strip().strip("/")
    base = (starting_branch or "main").strip() or "main"
    remote = branch.strip()
    return (
        "```bash\n"
        "cd ~/Storykeep\n"
        f"git remote add github https://github.com/{slug}.git 2>/dev/null || true\n"
        "git fetch github\n"
        f"git checkout {base}\n"
        f"git pull github {base}\n"
        f"git merge github/{remote}\n"
        f"git push github {base}\n"
        "```"
    )


def format_follow_up(
    snapshot: AgentRunSnapshot,
    *,
    agent_url: str,
    starting_branch: str = "main",
    stale: bool = False,
) -> str | None:
    """Chat text for a finished, failed, missing, or stale run. None while it is still running."""
    url = (agent_url or "").strip() or "(agent link from the earlier message)"
    if stale:
        return (
            "Cloud Agent update\n\n"
            f"This run is still going. Open: {url}\n\n"
            "The branch name and merge commands will show up here when it finishes."
        )
    status_name = (snapshot.status or "").upper()
    if status_name == "MISSING":
        return (
            "Cloud Agent update\n\n"
            f"That agent is no longer on Cursor. Open: {url}"
        )
    if status_name not in TERMINAL_RUN_STATUSES:
        return None
    if status_name != "FINISHED":
        detail = (snapshot.result or "").strip() or "No result text came back."
        return (
            "Cloud Agent update\n\n"
            f"The run ended with status {status_name}. Open: {url}\n\n"
            f"{detail[:1200]}"
        )
    changed = " ".join((snapshot.result or "").split())
    if len(changed) > 1200:
        changed = changed[:1200].rstrip() + "…"
    if not changed:
        changed = "The agent finished without a written summary. Open the link to review the diff."
    lines = [
        "Cloud Agent update",
        "",
        f"Finished. Open: {url}",
        "",
        f"What changed: {changed}",
    ]
    if snapshot.pr_url:
        lines.extend(["", f"Pull request: {snapshot.pr_url}", "You can merge that on GitHub, or use the commands below."])
    if snapshot.branch:
        lines.extend(
            [
                "",
                f"Branch: `{snapshot.branch}`",
                "",
                "Ubuntu — merge that branch into main:",
                "",
                merge_commands(snapshot.branch, starting_branch=starting_branch),
                "",
                "Then in this chat: Show GitHub status, then deploy Storykeep.",
            ]
        )
    else:
        lines.extend(["", "No cursor/ branch was listed yet. Open the agent link and check Branches on GitHub."])
    return "\n".join(lines)


def execute_tool_call(call: dict[str, Any], *, source_message: str | None = None) -> str:
    name = call.get("name")
    if name != START_TOOL_NAME:
        return "Unknown Cursor tool."
    outcome = start_agent(
        str(call.get("prompt") or ""),
        branch=str(call.get("branch") or "") or None,
        auto_create_pr=call.get("auto_create_pr") if "auto_create_pr" in call else None,
        source_message=source_message,
    )
    return format_start_for_model(outcome)
