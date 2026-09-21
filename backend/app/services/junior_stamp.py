from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

NEW_YORK = ZoneInfo("America/New_York")
_STAMP_HEAD_RE = re.compile(r"^UTC:\s*\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+ET\s+\([A-Z]{3,4}\):", re.I)


def format_junior_bubble_stamp(now: datetime | None = None) -> str:
    """First line for a saved Junior assistant bubble."""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    utc = instant.astimezone(timezone.utc)
    eastern = instant.astimezone(NEW_YORK)
    tz_label = eastern.tzname() or "ET"
    return (
        f"UTC: {utc.strftime('%Y-%m-%d %H:%M')}    "
        f"ET ({tz_label}): {eastern.strftime('%Y-%m-%d %H:%M')}"
    )


def stamp_assistant_content(content: str, *, now: datetime | None = None) -> str:
    """Prepend the server UTC/ET stamp to a finalized assistant reply."""
    text = (content or "").strip()
    if not text:
        return text
    first = text.split("\n", 1)[0].strip()
    if _STAMP_HEAD_RE.match(first):
        return text
    return f"{format_junior_bubble_stamp(now)}\n{text}"
