"""One chat turn: today's calendar, unread mail, and pinned Schoolwork notes."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, Feed, Folder, User
from app.services.destination import apply_shelf_filter

MORNING_TZ = ZoneInfo("America/New_York")
MAIL_CAP = 8
NOTE_CAP = 12

MORNING_RE = re.compile(
    r"\b(?:"
    r"what(?:'s| is) on today|"
    r"whats on today|"
    r"school morning|"
    r"morning line|"
    r"what(?:'s| is) due today|"
    r"today(?:'s|s)? school"
    r")\b",
    re.I,
)


def wants_morning(message: str) -> bool:
    return bool(MORNING_RE.search(message or ""))


def today_window(now: datetime | None = None) -> tuple[datetime, datetime, str]:
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    local = instant.astimezone(MORNING_TZ)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    label = start.strftime("%A, %B ") + str(start.day)
    return start, end, label


def _clock(start: str) -> str:
    raw = (start or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    local = parsed.astimezone(MORNING_TZ)
    hour = local.strftime("%I").lstrip("0") or "12"
    return f"{hour}:{local.strftime('%M %p').lower()}"


def format_morning(
    *,
    date_label: str,
    events: list[dict] | None,
    calendar_connected: bool,
    calendar_error: bool = False,
    mail_items: list[dict] | None,
    mail_total: int = 0,
    mail_connected: bool,
    mail_error: bool = False,
    notes: list[tuple[str, str | None]] | None,
    notes_error: bool = False,
) -> str:
    lines = [f"School morning — {date_label}", "", "Today"]
    if not calendar_connected:
        lines.append("- Calendar is not connected. Open Calendar in StoryKeep.")
    elif calendar_error:
        lines.append("- Calendar could not be read this turn.")
    elif not events:
        lines.append("- Nothing on the calendar.")
    else:
        for item in events[:20]:
            title = str(item.get("title") or "Untitled").strip() or "Untitled"
            when = _clock(str(item.get("start") or ""))
            lines.append(f"- {when} — {title}" if when else f"- {title}")
    lines.extend(["", "Unread mail"])
    if not mail_connected:
        lines.append("- Mail is not connected. Open Mail in StoryKeep.")
    elif mail_error:
        lines.append("- Unread mail could not be read this turn.")
    elif not mail_items:
        lines.append("- No unread mail.")
    else:
        shown = mail_items[:MAIL_CAP]
        for item in shown:
            who = str(item.get("from") or "(unknown)").strip() or "(unknown)"
            subject = str(item.get("subject") or "(no subject)").strip() or "(no subject)"
            lines.append(f"- {who} — {subject}")
        extra = max(0, mail_total - len(shown))
        if extra:
            lines.append(f"- {extra} more unread")
    lines.extend(["", "Pinned Schoolwork"])
    if notes_error:
        lines.append("- Pinned notes could not be read this turn.")
    elif not notes:
        lines.append("- No pinned notes on the Schoolwork shelf.")
    else:
        for title, folder in notes[:NOTE_CAP]:
            name = (title or "Untitled").strip() or "Untitled"
            if folder:
                lines.append(f"- {name} ({folder})")
            else:
                lines.append(f"- {name}")
    return "\n".join(lines)


def pinned_schoolwork(db: Session, user: User) -> list[tuple[str, str | None]]:
    stmt = apply_shelf_filter(
        select(Article.title, Folder.name)
        .join(Feed, Article.feed_id == Feed.id)
        .outerjoin(Folder, Article.folder_id == Folder.id)
        .where(Feed.user_id == user.id, Article.pinned.is_(True), Article.is_correction.is_(False)),
        "schoolwork",
    )
    stmt = stmt.order_by(Article.pinned_at.desc().nulls_last(), Article.title.asc()).limit(NOTE_CAP)
    rows = db.execute(stmt).all()
    return [(str(title or ""), folder if isinstance(folder, str) else None) for title, folder in rows]


def build(db: Session, user: User, *, now: datetime | None = None) -> str:
    from app.services import calendar_access as calendars
    from app.services import fastmail_jmap as jmap
    from app.services import mail as mail_service

    start, end, label = today_window(now)
    calendar_connected = calendars.is_connected(db, user.id)
    events: list[dict] | None = []
    calendar_error = False
    if calendar_connected:
        try:
            events = calendars.list_events(
                db,
                user.id,
                time_min=start.isoformat(),
                time_max=end.isoformat(),
                timezone_name="America/New_York",
            )
        except Exception:
            events = None
            calendar_error = True
    mail_connected = mail_service.has_token(db, user)
    mail_items: list[dict] | None = []
    mail_total = 0
    mail_error = False
    if mail_connected:
        try:
            listed = jmap.list_emails(mail_service.require_token(db, user), role="inbox", unseen=True, limit=50)
            mail_items = list(listed.get("items") or [])
            mail_total = int(listed.get("total") or len(mail_items))
        except Exception:
            mail_items = None
            mail_error = True
    notes: list[tuple[str, str | None]] | None = []
    notes_error = False
    try:
        notes = pinned_schoolwork(db, user)
    except Exception:
        notes = None
        notes_error = True
    return format_morning(
        date_label=label,
        events=events,
        calendar_connected=calendar_connected,
        calendar_error=calendar_error,
        mail_items=mail_items,
        mail_total=mail_total,
        mail_connected=mail_connected,
        mail_error=mail_error,
        notes=notes,
        notes_error=notes_error,
    )
