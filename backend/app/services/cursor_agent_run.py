"""Owns Cloud Agent run snapshots (the AgentRunSnapshot model and run-fetching logic) extracted from cursor_agent_tool."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from app.services.cursor_agent_transport import _get


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
