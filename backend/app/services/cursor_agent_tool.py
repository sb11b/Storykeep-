from __future__ import annotations

import logging

from app.services.cursor_agent_instructions import merge_commands
from app.services.cursor_agent_run import AgentRunSnapshot, TERMINAL_RUN_STATUSES
# Re-exported from cursor_agent_transport so existing callers
# (chat_stream, junior_model, cursor_agent_watch) keep resolving
# cursor_agent_tool.<name>; the canonical home is cursor_agent_transport.
from app.services.cursor_agent_transport import TIMEOUT_SEC, configured, owner_can_use
# Re-exported from cursor_agent_start so existing callers keep resolving
# cursor_agent_tool.<name>; the canonical home is cursor_agent_start
# (extracted start cluster: constants, response formatting, entry points).
from app.services.cursor_agent_start import (
    CURSOR_OFF_APPEND,
    CURSOR_ON_APPEND,
    execute_tool_call,
    start_agent,
)

logger = logging.getLogger(__name__)


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
