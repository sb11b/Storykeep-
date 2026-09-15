from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import JuniorMemory, User
from app.services.demo_lock import is_locked

OWNER_EMAIL = "stevebitsko@duck.com"
MEMORY_ATTACH_CHARS = 8_000
MEMORY_SAVE_CHARS = 100_000
SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "steve_junior_memory.md"

MEMORY_SYSTEM_PREFIX = """Steve's Junior memory (one owner note — standing context).
Do not dump this note into the reply. Do not print a UI footer. Never say “Use Add to notes”.
"""


def _seed_markdown() -> str:
    try:
        return SEED_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def owner_email(user: User | None) -> str:
    return (getattr(user, "email", None) or "").strip().lower()


def can_use_memory(user: User | None) -> bool:
    if user is None or is_locked(user):
        return False
    return True


def get_row(db: Session, user_id: UUID) -> JuniorMemory | None:
    return db.get(JuniorMemory, user_id)


def markdown_for(db: Session, user: User) -> str:
    if not can_use_memory(user):
        return ""
    row = get_row(db, user.id)
    if row is None:
        return ""
    return (getattr(row, "markdown", None) or "") or ""


def system_section(db: Session, user: User) -> str | None:
    if not can_use_memory(user):
        return None
    body = markdown_for(db, user).strip()
    if not body:
        return None
    if len(body) > MEMORY_ATTACH_CHARS:
        body = body[:MEMORY_ATTACH_CHARS].rstrip() + "\n…"
    return f"{MEMORY_SYSTEM_PREFIX}\n{body}"


def save_markdown(db: Session, user: User, markdown: str) -> JuniorMemory:
    if not can_use_memory(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo accounts cannot use Junior memory.")
    text = (markdown or "").replace("\x00", "")
    if len(text) > MEMORY_SAVE_CHARS:
        raise HTTPException(status_code=400, detail="Memory note is too long.")
    row = get_row(db, user.id)
    now = datetime.now(timezone.utc)
    if row is None:
        row = JuniorMemory(user_id=user.id, markdown=text, updated_at=now)
        db.add(row)
    else:
        row.markdown = text
        row.updated_at = now
    db.flush()
    return row


def seed_steve_memory(db: Session) -> None:
    user = db.scalar(select(User).where(func.lower(User.email) == OWNER_EMAIL))
    if user is None or is_locked(user):
        return
    blob = _seed_markdown()
    if not blob:
        return
    row = get_row(db, user.id)
    if row and (row.markdown or "").strip():
        return
    if row is None:
        row = JuniorMemory(user_id=user.id, markdown=blob)
        db.add(row)
    else:
        row.markdown = blob
        row.updated_at = datetime.now(timezone.utc)
    db.flush()
