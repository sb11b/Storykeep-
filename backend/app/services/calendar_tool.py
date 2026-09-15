from __future__ import annotations

import json
import re
from datetime import datetime

ADD_EVENT_NAME = "add_event"

ADD_EVENT_TOOL = {
    "type": "function",
    "function": {
        "name": ADD_EVENT_NAME,
        "description": "Propose a Google Calendar event. StoryKeep asks Steve to Confirm before writing anything.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Event title"},
                "start": {"type": "string", "description": "ISO 8601 start datetime with offset"},
                "end": {"type": "string", "description": "ISO 8601 end datetime with offset"},
            },
            "required": ["title", "start", "end"],
        },
    },
}

CALENDAR_ON_APPEND = """
Steve connected Google Calendar. When he asks to schedule or add an event, call the add_event tool with title, start, and end as ISO 8601 datetimes (include the timezone offset). Do not say the event is already on the calendar. StoryKeep will show Confirm before writing. Never request Gmail, IMAP, or a mailbox password.
If you cannot call tools, reply with only this fence:
```storykeep-event
{"title":"...","start":"...","end":"..."}
```
Do not invent a Google confirmation number.
"""

CALENDAR_OFF_APPEND = """
Steve has not connected Google Calendar. If he asks to add a calendar event, tell him to open Calendar in the StoryKeep library and click Connect Google. Do not invent a confirmation. Do not ask for a Gmail or IMAP password.
"""

CALENDAR_FENCE = re.compile(r"```(?:storykeep-event|json)\s*(\{[\s\S]*?\})\s*```", re.I)


def _parse_when(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None
    cleaned = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.isoformat()
    return parsed.isoformat()


def normalize_add_event(payload: object) -> dict[str, str] | None:
    if not isinstance(payload, dict):
        return None
    inner = payload.get("add_event") if isinstance(payload.get("add_event"), dict) else payload
    if not isinstance(inner, dict):
        return None
    title = str(inner.get("title") or inner.get("summary") or "").strip()
    start = _parse_when(str(inner.get("start") or inner.get("start_time") or ""))
    end = _parse_when(str(inner.get("end") or inner.get("end_time") or ""))
    if not title or not start or not end:
        return None
    if len(title) > 400:
        title = title[:400]
    return {"title": title, "start": start, "end": end}


def extract_calendar_proposal(text: str | None) -> dict[str, str] | None:
    blob = text or ""
    match = CALENDAR_FENCE.search(blob)
    if match:
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            parsed = None
        found = normalize_add_event(parsed)
        if found:
            return found
    stripped = blob.strip()
    if stripped.startswith("{") and "start" in stripped:
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None
        found = normalize_add_event(parsed)
        if found:
            return found
    return None


def assemble_tool_calls(fragments: list[dict]) -> dict[str, str] | None:
    buckets: dict[int, dict[str, str]] = {}
    for item in fragments:
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
    for slot in buckets.values():
        if slot.get("name") != ADD_EVENT_NAME:
            continue
        try:
            parsed = json.loads(slot.get("arguments") or "{}")
        except json.JSONDecodeError:
            continue
        found = normalize_add_event(parsed)
        if found:
            return found
    return None
