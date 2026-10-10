from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from app.services.cursor_agent_instructions import (
    _cursor_api_error_detail,
    merge_commands,
    push_workflow_for_user,
)
from app.services.cursor_agent_calls import START_TOOL_NAME
from app.services.cursor_agent_outcome import CursorAgentOutcome, format_start_for_model
from app.services.cursor_agent_intent import _default_branch, _valid_branch_ref, extract_branch, extract_prompt
from app.services.cursor_agent_replies import diverged_ff_reply
# Re-exported from cursor_agent_transport so existing callers
# (chat_stream, junior_model, cursor_agent_watch) keep resolving
# cursor_agent_tool.<name>; the canonical home is cursor_agent_transport.
from app.services.cursor_agent_transport import (
    TIMEOUT_SEC,
    _analytics_get,
    _api_key,
    _get,
    _post,
    _repo_slug,
    _repo_url,
    _request,
    configured,
    owner_can_use,
    reject_demo,
)

logger = logging.getLogger(__name__)

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
