from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, Feed, GrokAutomation, GrokAutomationRun, GrokWorkspaceFile, User
from app.services import chat as chat_service
from app.services.demo_lock import reject_locked

logger = logging.getLogger(__name__)

SCHEDULES = ("once", "daily", "weekdays", "weekly", "monthly", "yearly")
TRIGGERS = ("schedule", "email")
NOTIFIES = ("none", "email", "app", "both")
FILE_CAP = 80_000
FILE_COUNT_CAP = 40
PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,180}$")

TEMPLATES: list[dict[str, object]] = [
    {
        "id": "morning-brief",
        "title": "Morning archive brief",
        "instruction": "Summarize what Steve should read first today. Prefer unread StoryKeep items if they are listed. Keep it under 180 words. End with three concrete next steps.",
        "trigger": "schedule",
        "schedule": "daily",
        "hour": 8,
        "minute": 0,
        "include_unread": True,
        "notify": "app",
    },
    {
        "id": "weekday-school",
        "title": "Weekday school check",
        "instruction": "Write a short school-coding standup: one concept to review, one practice problem, and one thing to file in Schoolwork. No fluff.",
        "trigger": "schedule",
        "schedule": "weekdays",
        "hour": 16,
        "minute": 30,
        "include_unread": False,
        "notify": "app",
    },
    {
        "id": "weekly-vault",
        "title": "Sunday vault digest",
        "instruction": "Draft a weekly digest of Steve's reading life: themes, open questions, and what belongs in Vault vs Notes. Be specific.",
        "trigger": "schedule",
        "schedule": "weekly",
        "hour": 10,
        "minute": 0,
        "weekday": 6,
        "include_unread": True,
        "notify": "email",
    },
    {
        "id": "invoice-mail",
        "title": "Flag invoice email",
        "instruction": "An email just arrived. Extract vendor, amount, due date, and whether Steve should pay, query, or file it. Quote only facts from the email.",
        "trigger": "email",
        "schedule": "daily",
        "email_subject": "invoice",
        "include_unread": False,
        "notify": "both",
    },
]

DEFAULT_FILES = {
    "README.md": (
        "# Grok Build workspace\n\n"
        "This is Steve's StoryKeep coding pad. Grok Build edits these files in place.\n\n"
        "- `src/hello.py` — start here\n"
        "- `notes/inbox.md` — scratch\n"
        "- `AGENTS.md` — how the agent should behave\n"
    ),
    "AGENTS.md": (
        "# Agent notes\n\n"
        "- Prefer small, working Python 3.12 scripts.\n"
        "- Do not invent StoryKeep APIs that are not in this workspace.\n"
        "- When changing files, return a patches JSON block the IDE can apply.\n"
    ),
    "src/hello.py": (
        '"""Starter script for the Grok Build IDE."""\n\n'
        "def greet(name: str) -> str:\n"
        '    return f"hello, {name}"\n\n\n'
        'if __name__ == "__main__":\n'
        '    print(greet("Steve"))\n'
    ),
    "notes/inbox.md": "# Inbox\n\nDrop ideas here. Ask Build to turn them into code.\n",
}

PLAN_SYSTEM = """You are Grok Build inside StoryKeep's IDE.
Steve is a student. Plan first: return ONLY a JSON object:
{"plan":[{"id":"1","title":"...","detail":"..."}]}
Do not write code yet. 3 to 7 steps. No markdown outside the JSON."""

BUILD_SYSTEM = """You are Grok Build inside StoryKeep's IDE.
Edit the workspace files. Return a short explanation, then a fenced json block:
```json
{"patches":[{"path":"src/hello.py","content":"full file contents"}]}
```
Only patch files that must change. Paths stay inside the workspace. No secrets."""


def sanitize_path(path: str) -> str:
    cleaned = (path or "").replace("\\", "/").strip().lstrip("/")
    if not cleaned or ".." in cleaned.split("/") or cleaned.startswith("/"):
        raise HTTPException(status_code=400, detail="That file path is not allowed.")
    if not PATH_RE.match(cleaned):
        raise HTTPException(status_code=400, detail="Use a simple path like src/hello.py.")
    return cleaned


def extract_json_object(text: str) -> dict | None:
    raw = (text or "").strip()
    if not raw:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", raw)
    blob = fenced.group(1) if fenced else None
    if blob is None:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            blob = raw[start : end + 1]
    if not blob:
        return None
    try:
        parsed = json.loads(blob)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_plan(text: str) -> list[dict[str, str]]:
    parsed = extract_json_object(text) or {}
    rows = parsed.get("plan")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    for index, item in enumerate(rows, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or f"Step {index}").strip()
        detail = str(item.get("detail") or "").strip()
        ident = str(item.get("id") or index)
        if title:
            out.append({"id": ident, "title": title, "detail": detail})
    return out[:12]


def parse_patches(text: str) -> list[dict[str, str]]:
    parsed = extract_json_object(text) or {}
    rows = parsed.get("patches")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        try:
            path = sanitize_path(str(item.get("path") or ""))
        except HTTPException:
            continue
        content = item.get("content")
        if not isinstance(content, str):
            continue
        if len(content) > FILE_CAP:
            content = content[:FILE_CAP]
        out.append({"path": path, "content": content})
    return out[:20]


def next_run_at(
    *,
    trigger: str,
    schedule: str,
    hour: int,
    minute: int,
    weekday: int,
    monthday: int,
    tz_name: str,
    after: datetime | None = None,
) -> datetime | None:
    if trigger != "schedule":
        return None
    try:
        zone = ZoneInfo(tz_name or "America/New_York")
    except Exception:
        zone = ZoneInfo("America/New_York")
    now = (after or datetime.now(timezone.utc)).astimezone(zone)
    hour = min(23, max(0, int(hour)))
    minute = min(59, max(0, int(minute)))
    weekday = min(6, max(0, int(weekday)))
    monthday = min(28, max(1, int(monthday)))

    def at(day: datetime) -> datetime:
        return day.replace(hour=hour, minute=minute, second=0, microsecond=0)

    candidate = at(now)
    if schedule == "once":
        if candidate <= now:
            candidate = candidate + timedelta(days=1)
        return candidate.astimezone(timezone.utc)
    if schedule == "daily":
        if candidate <= now:
            candidate = candidate + timedelta(days=1)
        return candidate.astimezone(timezone.utc)
    if schedule == "weekdays":
        while candidate <= now or candidate.weekday() >= 5:
            candidate = candidate + timedelta(days=1)
            candidate = at(candidate)
        return candidate.astimezone(timezone.utc)
    if schedule == "weekly":
        while candidate <= now or candidate.weekday() != weekday:
            candidate = candidate + timedelta(days=1)
            candidate = at(candidate)
        return candidate.astimezone(timezone.utc)
    if schedule == "monthly":
        while candidate <= now or candidate.day != monthday:
            candidate = candidate + timedelta(days=1)
            candidate = at(candidate)
        return candidate.astimezone(timezone.utc)
    if schedule == "yearly":
        while candidate <= now or candidate.month != 1 or candidate.day != monthday:
            candidate = candidate + timedelta(days=1)
            candidate = at(candidate)
        return candidate.astimezone(timezone.utc)
    return candidate.astimezone(timezone.utc)


def owned_automation(db: Session, user: User, automation_id: UUID) -> GrokAutomation:
    row = db.get(GrokAutomation, automation_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="Automation not found.")
    return row


def seed_workspace(db: Session, user: User) -> list[GrokWorkspaceFile]:
    existing = list(db.scalars(select(GrokWorkspaceFile).where(GrokWorkspaceFile.user_id == user.id)))
    if existing:
        return existing
    rows: list[GrokWorkspaceFile] = []
    for path, content in DEFAULT_FILES.items():
        row = GrokWorkspaceFile(user_id=user.id, path=path, content=content)
        db.add(row)
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def unread_digest(db: Session, user: User, limit: int = 8) -> str:
    rows = db.scalars(
        select(Article)
        .join(Feed, Article.feed_id == Feed.id)
        .where(Feed.user_id == user.id, Article.is_read.is_(False))
        .order_by(Article.published_at.desc().nullslast(), Article.created_at.desc())
        .limit(limit)
    ).all()
    if not rows:
        return "No unread articles in StoryKeep right now."
    lines = [f"- {item.title or 'Untitled'}" for item in rows]
    return "Unread in StoryKeep:\n" + "\n".join(lines)


def execute_automation(
    db: Session,
    automation: GrokAutomation,
    *,
    trigger: str,
    email_context: str | None = None,
) -> GrokAutomationRun:
    user = db.get(User, automation.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    reject_locked(user)
    chat_service.enforce_rate_limit(user.id)
    parts = [automation.instruction.strip()]
    if automation.include_unread:
        parts.append(unread_digest(db, user))
    if email_context:
        parts.append("Incoming email:\n" + email_context.strip())
    prompt = "\n\n".join(part for part in parts if part)
    status = "ok"
    output = ""
    error = None
    model = None
    reasoning = None
    try:
        result = chat_service.complete_once(
            [{"role": "system", "content": "You are Grok running a saved StoryKeep automation for Steve."},
             {"role": "user", "content": prompt}],
            reasoning_effort="low",
            max_tokens=900,
        )
        output = result["text"]
        model = result["model"]
        reasoning = result["reasoning"]
    except HTTPException as exc:
        status = "error"
        error = str(exc.detail)
        output = error or "Run failed."
    except Exception as exc:
        status = "error"
        error = str(exc)
        output = error
        logger.exception("Automation run failed id=%s", automation.id)
    run = GrokAutomationRun(
        automation_id=automation.id,
        status=status,
        trigger=trigger,
        email_context=(email_context or "").strip() or None,
        output=output,
        error=error,
        model=model,
        reasoning=reasoning,
    )
    db.add(run)
    now = datetime.now(timezone.utc)
    automation.last_run_at = now
    automation.updated_at = now
    if automation.trigger == "schedule":
        if automation.schedule == "once":
            automation.enabled = False
            automation.next_run_at = None
        else:
            automation.next_run_at = next_run_at(
                trigger=automation.trigger,
                schedule=automation.schedule,
                hour=automation.hour,
                minute=automation.minute,
                weekday=automation.weekday,
                monthday=automation.monthday,
                tz_name=automation.timezone,
                after=now,
            )
    db.add(automation)
    db.commit()
    db.refresh(run)
    return run


def run_due_automations() -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        due = db.scalars(
            select(GrokAutomation).where(
                GrokAutomation.enabled.is_(True),
                GrokAutomation.trigger == "schedule",
                GrokAutomation.next_run_at.is_not(None),
                GrokAutomation.next_run_at <= now,
            )
        ).all()
        for row in due:
            try:
                execute_automation(db, row, trigger="schedule")
            except Exception:
                logger.exception("Due automation failed id=%s", row.id)
    finally:
        db.close()
