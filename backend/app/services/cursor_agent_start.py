"""Owns the Cursor Cloud Agent start flow (prompt-append constants, response formatting, start and tool-call entry points) extracted from cursor_agent_tool."""
from __future__ import annotations

from typing import Any
from urllib.parse import quote

from app.services.cursor_agent_instructions import _cursor_api_error_detail, push_workflow_for_user
from app.services.cursor_agent_calls import START_TOOL_NAME
from app.services.cursor_agent_outcome import CursorAgentOutcome, format_start_for_model
from app.services.cursor_agent_intent import _default_branch, _valid_branch_ref, extract_branch, extract_prompt
from app.services.cursor_agent_replies import diverged_ff_reply
from app.services.cursor_agent_transport import _post, _repo_url, configured

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
