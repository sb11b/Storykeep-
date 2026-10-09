from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CursorAgentOutcome:
    ok: bool
    text: str
    status_code: int = 200
    agent_id: str | None = None
    agent_url: str | None = None
    run_id: str | None = None


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

