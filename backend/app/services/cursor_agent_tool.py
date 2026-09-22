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
- Use ONLY when Steve explicitly asks to start/launch/open/spawn/run-in a Cursor or Cloud Agent — NOT when he only wants a copy-paste prompt block.
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
    r"cursor\s+(?:cloud\s+)?agent\s+task"
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
    },
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


def wants_start(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if wants_cursor_setup(text):
        return True
    return bool(_START_RE.search(text))


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


def _post(path: str, payload: dict[str, Any]) -> tuple[int, Any]:
    key = _api_key()
    if not key:
        return 503, {"message": "Cursor API key not configured"}
    url = f"{_api_root()}{path}"
    try:
        with httpx.Client(timeout=TIMEOUT_SEC) as client:
            response = client.post(url, headers=_headers(), json=payload)
    except httpx.TimeoutException:
        return 504, {"message": "Cursor API timeout"}
    except httpx.HTTPError as exc:
        return 502, {"message": f"Cursor transport error: {exc}"}
    try:
        body = response.json()
    except json.JSONDecodeError:
        body = {"message": response.text[:500]}
    return response.status_code, body


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
    return CursorAgentOutcome(True, "\n".join(lines), status_code, agent_id, agent_url)


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
        bits = ["Cursor Cloud Agent started."]
        if outcome.agent_id:
            bits.append(f"Agent id: {outcome.agent_id}.")
        bits.append(f"Open: {outcome.agent_url}")
        return " ".join(bits)
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
