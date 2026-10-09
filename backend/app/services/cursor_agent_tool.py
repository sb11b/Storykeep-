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
from app.services.cursor_agent_intent import _default_branch, _valid_branch_ref, extract_branch, extract_prompt
from app.services.cursor_agent_replies import diverged_ff_reply

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

_BUGBOT_PR_NOTE = (
    "\n\nWhen this run pushes a cursor/* branch, open a pull request into main. "
    "CodeRabbit reviews that pull request. Bugbot is off. "
    "Do not comment bugbot run. Do not ask Steve to turn Bugbot on. "
    "Security is already enabled and reviews that same pull request. "
    "PR Routing & Approval is already enabled and may assign reviewers. "
    "Leave automatic approval off. Do not approve the pull request. "
    "Do not merge the pull request. Do not push to main. "
    "Rollouts stays disabled. Do not enable Rollouts and do not add deploy hooks for it."
)
_SECURITY_PUSH_NOTE = (
    "\n\nBefore every git push, run the Security Review agent on the diff you are about to push. "
    "Wait until that review finishes. Put its findings in the pull request body. "
    "Do not push when the review reports a high-severity issue. "
    "Cursor Security is already enabled. Do not ask Steve to enable it, "
    "and do not enable the scheduled Vulnerability Scanner."
)
_SENIOR_REVIEW_NOTE = (
    "\n\nBefore every git push, delegate the diff to the senior-reviewer subagent "
    "in .cursor/agents/senior-reviewer.md. Wait until that review finishes. "
    "Put its findings in the pull request body. "
    "Do not push when that review reports a high-severity issue."
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
                    "description": "Open a pull request when the agent finishes so Bugbot can review it. Default true.",
                    "default": True,
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


def _analytics_key() -> str:
    return (settings.cursor_analytics_key or settings.cursor_api_key or "").strip()


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


def _analytics_get(path: str, params: dict[str, str]) -> tuple[int, Any]:
    """Analytics uses HTTP basic auth. The Cloud Agent calls keep using a bearer token."""
    key = _analytics_key()
    if not key:
        return 503, {"message": "Cursor API key not configured"}
    url = f"{_api_root()}{path}"
    try:
        with httpx.Client(timeout=TIMEOUT_SEC) as client:
            response = client.get(url, params=params, auth=(key, ""))
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
        "Existing clone in Cursor terminal. Abort a stuck merge first, then match GitHub main:\n"
        "```bash\n"
        "cd ~/Storykeep\n"
        "git merge --abort\n"
        f"git remote add github {repo_https} 2>/dev/null || true\n"
        "git fetch github\n"
        f"git checkout {starting_branch}\n"
        f"git reset --hard github/{starting_branch}\n"
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
        "Tell Steve the agent is running in this Storykeep chat and the result will show up here. "
        "Do not send him to a cursor.com URL. "
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
    blocked = diverged_ff_reply(source_message or "") or diverged_ff_reply(task)
    if blocked:
        return CursorAgentOutcome(False, blocked, 200)
    chosen = (branch or "").strip()
    if source_message and not _valid_branch_ref(chosen):
        chosen = extract_branch(source_message)
    ref = chosen if _valid_branch_ref(chosen) else _default_branch()
    repo_url = _repo_url()
    auto_pr = True if auto_create_pr is None else bool(auto_create_pr)
    if auto_pr and "Bugbot is off" not in task:
        task = task.rstrip() + _BUGBOT_PR_NOTE
    if "Before every git push, run the Security Review agent" not in task:
        task = task.rstrip() + _SECURITY_PUSH_NOTE
    if "senior-reviewer subagent" not in task:
        task = task.rstrip() + _SENIOR_REVIEW_NOTE
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


_IN_APP_START = (
    "Cursor Cloud Agent started.\n\n"
    "It is running in this Storykeep chat. Stay in this app.\n\n"
    "When it finishes, this chat gets what changed, the branch name, and the merge commands."
)


def summarize_agent_for_user(outcome: CursorAgentOutcome) -> str:
    """Plain reply when xAI stays silent after server-side agent start."""
    if outcome.ok and (outcome.agent_id or outcome.agent_url):
        return _IN_APP_START
    text = (outcome.text or "").strip()
    if not outcome.ok and text:
        if text.startswith("Cursor Cloud Agent create failed"):
            return text
        return f"Could not start Cursor Cloud Agent: {text.splitlines()[0][:400]}"
    if text:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("- Agent URL:") or stripped.startswith("- Agent id:"):
                return _IN_APP_START
        return text.splitlines()[0][:500]
    if outcome.ok:
        return _IN_APP_START
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
        "git merge --abort\n"
        f"git remote add github https://github.com/{slug}.git 2>/dev/null || true\n"
        "git fetch github\n"
        f"git checkout {base}\n"
        f"git reset --hard github/{base}\n"
        f"git merge --ff-only github/{remote}\n"
        f"git push github {base}\n"
        "```"
    )


def pr_number_from_url(url: str | None) -> int | None:
    match = re.search(r"/pull/(\d+)", url or "")
    if not match:
        return None
    return int(match.group(1))


def format_cost_cents(value: Any) -> str:
    if value is None or value == "":
        return "not billed"
    try:
        cents = float(value)
    except (TypeError, ValueError):
        return "not billed"
    if cents >= 100:
        return f"${cents / 100:.2f}"
    text = f"{cents:.1f}".rstrip("0").rstrip(".")
    return f"{text} cents"


def _finding_lines(bug: dict[str, Any], index: int, *, dry_run: bool) -> list[str]:
    severity = str(bug.get("severity") or "").strip()
    title = str(bug.get("title") or "").strip()
    comment_id = bug.get("comment_id")
    posted = not dry_run and comment_id not in (None, "")
    if posted:
        status_name = str(bug.get("resolution_status") or "unknown").strip() or "unknown"
        parts = [part for part in (severity, status_name, f"comment {comment_id}") if part]
        lines = [f"{index}. {' — '.join(parts)}"]
        if title:
            lines.append(f"   {title}")
        description = " ".join(str(bug.get("description") or "").split())
        if description:
            lines.append(f"   {description[:400]}")
        lines.extend(_location_lines(bug.get("locations")))
        return lines
    head = title or "Finding"
    prefix = f"{index}. {severity} — {head}" if severity else f"{index}. {head}"
    lines = [prefix]
    description = " ".join(str(bug.get("description") or "").split())
    if description:
        lines.append(f"   {description[:400]}")
    lines.extend(_location_lines(bug.get("locations")))
    return lines


def _location_lines(locations: Any) -> list[str]:
    rows = locations if isinstance(locations, list) else []
    lines: list[str] = []
    for loc in rows:
        if not isinstance(loc, dict):
            continue
        file_name = str(loc.get("file") or "").strip()
        start_line = loc.get("start_line")
        end_line = loc.get("end_line")
        if file_name and start_line and end_line and start_line != end_line:
            lines.append(f"   {file_name}:{start_line}-{end_line}")
        elif file_name and start_line:
            lines.append(f"   {file_name}:{start_line}")
        elif file_name:
            lines.append(f"   {file_name}")
    return lines


def format_bugbot_reviews(reviews: list[Any]) -> str:
    rows = [item for item in reviews if isinstance(item, dict)]
    rows.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    blocks = ["Review analytics", ""]
    for review in rows[:5]:
        sha = str(review.get("commit_sha") or "").strip()
        short = sha[:12] if sha else "unknown"
        found = review.get("bugs_found")
        dry = bool(review.get("dry_run")) or str(review.get("publication_status") or "") == "dry_run"
        number = review.get("pr_number")
        blocks.append("Dry run" if dry else "Posted review")
        if number not in (None, ""):
            blocks.append(f"Pull request: {number}")
        blocks.append(f"Commit: {short}")
        blocks.append(f"Findings: {found if found is not None else 0}")
        if review.get("show_cost", True):
            blocks.append(f"Cost: {format_cost_cents(review.get('cost_cents'))}")
        bugs = review.get("bugs") if isinstance(review.get("bugs"), list) else []
        for index, bug in enumerate(bugs, start=1):
            if isinstance(bug, dict):
                blocks.extend(_finding_lines(bug, index, dry_run=dry))
        blocks.append("")
    return "\n".join(blocks).strip()


def fetch_bugbot_reviews(pr_number: int, *, repo_slug: str | None = None) -> tuple[list[dict[str, Any]], str | None]:
    """Return reviews and a user-facing error. An empty list with no error means Bugbot is not done yet."""
    slug = (repo_slug or _repo_slug()).strip().strip("/")
    host_repo = slug if "/" in slug and slug.split("/")[0].endswith(".com") else f"github.com/{slug}"
    status_code, body = _analytics_get(
        "/analytics/team/bugbot-reviews",
        {
            "repo": host_repo,
            "prNumber": str(pr_number),
            "page": "1",
            "pageSize": "20",
        },
    )
    if status_code >= 400 or not isinstance(body, dict):
        return [], None
    data = body.get("data")
    if not isinstance(data, list):
        return [], None
    reviews = []
    for item in data:
        if not isinstance(item, dict):
            continue
        listed = item.get("pr_number")
        if listed not in (None, "", pr_number, str(pr_number)):
            continue
        reviews.append(item)
    return reviews, None


def bugbot_section(pr_url: str | None, *, repo_slug: str | None = None) -> tuple[str, bool]:
    """Chat block and whether waiting should stop. Empty text means the review is not ready."""
    number = pr_number_from_url(pr_url)
    if number is None:
        return "", True
    reviews, _error = fetch_bugbot_reviews(number, repo_slug=repo_slug)
    if not reviews:
        from app.services import github_tool

        fallback = github_tool.bugbot_pull_review(number)
        if fallback:
            reviews = [fallback]
    if not reviews:
        return "", False
    return format_bugbot_reviews(reviews), True


def format_follow_up(
    snapshot: AgentRunSnapshot,
    *,
    agent_url: str,
    starting_branch: str = "main",
    stale: bool = False,
    bugbot_text: str | None = None,
) -> str | None:
    """Chat text for a finished, failed, missing, or stale run. None while it is still running."""
    del agent_url
    if stale:
        return (
            "Cloud Agent update\n\n"
            "This run is still going in this Storykeep chat.\n\n"
            "The branch name and merge commands will show up here when it finishes."
        )
    status_name = (snapshot.status or "").upper()
    if status_name == "MISSING":
        return (
            "Cloud Agent update\n\n"
            "That agent is no longer running. This chat has the last update."
        )
    if status_name not in TERMINAL_RUN_STATUSES:
        return None
    if status_name != "FINISHED":
        detail = (snapshot.result or "").strip() or "No result text came back."
        return (
            "Cloud Agent update\n\n"
            f"The run ended with status {status_name}. The result is in this chat.\n\n"
            f"{detail[:1200]}"
        )
    changed = " ".join((snapshot.result or "").split())
    if len(changed) > 1200:
        changed = changed[:1200].rstrip() + "…"
    if not changed:
        changed = "The agent finished without a written summary. The result is in this chat."
    lines = [
        "Cloud Agent update",
        "",
        "Finished. The result is in this chat.",
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
        lines.extend(["", "No cursor/ branch was listed yet. Ask in this chat: Show GitHub status."])
    if bugbot_text and bugbot_text.strip():
        lines.extend(["", bugbot_text.strip()])
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
