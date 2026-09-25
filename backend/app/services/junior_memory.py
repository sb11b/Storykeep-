from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import JuniorMemory, User
from app.services.demo_lock import is_locked

OWNER_EMAIL = "angry.tune8751@fastmail.com"
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


STALE_CURSOR_TASK_MARK = "polish his text into one copy-paste block"
CURSOR_PROMPT_SECTION = """## Prompt for Cursor

Same rules for **typed or dictated (STT)** input:

1. **Steve asks you to write one** (“write a prompt for Cursor…”) — one complete copy-paste block: goal, context, constraints, files, done-when. Fold in any details he already said. Do not start an agent.
2. **Steve supplied the task** (pasted or spoke the work) — the server starts a Cloud Agent and the reply is the agent URL. Do not replace that with a copy-paste prompt. Do not say you cannot start an agent from this chat. Do not say the key is missing.
3. **Steve asks to start, launch, go ahead and send, or send the next step** — the server starts it. Return the agent URL and the Ubuntu push steps. Never tell him to copy a prompt into Cursor.
4. **After a start,** this same chat gets a follow-up when the run finishes: branch name, what changed, and the merge commands. Do not invent that follow-up before it is in the thread.
"""
CURSOR_DELEGATE_OLD = (
    "- **Owner Cursor delegate (Steve only):** when configured, I can **start a real Cursor Cloud Agent** "
    "on sb11b/Storykeep- and return the agent link (https://cursor.com/agents/bc-...). "
    "You still edit/push in Cursor or via that agent — I do not edit the repo from this bubble."
)
CURSOR_DELEGATE_NEW = (
    CURSOR_DELEGATE_OLD
    + " A code task you already wrote also starts an agent when the key is set. "
    "When the run finishes, I post the branch name, what changed, and the Ubuntu merge commands in that same chat."
)


def apply_cursor_memory_fix(markdown: str) -> str | None:
    """Replace the stale copy-paste rule. None when the note already matches."""
    text = markdown or ""
    if (
        STALE_CURSOR_TASK_MARK not in text
        and "when the run finishes" in text
        and "send the next step" in text.lower()
    ):
        return None
    updated = text
    if CURSOR_DELEGATE_OLD in updated and "when the run finishes" not in updated:
        updated = updated.replace(CURSOR_DELEGATE_OLD, CURSOR_DELEGATE_NEW, 1)
    if STALE_CURSOR_TASK_MARK not in updated:
        return updated if updated != text else None
    heading = "## Prompt for Cursor"
    start = updated.find(heading)
    replacement = CURSOR_PROMPT_SECTION.strip() + "\n"
    if start < 0:
        updated = updated.rstrip() + "\n\n" + replacement
    else:
        rest = updated[start + len(heading) :]
        import re

        match = re.search(r"\n## ", rest)
        end = start + len(heading) + match.start() if match else len(updated)
        tail = updated[end:]
        updated = updated[:start] + replacement + ("" if tail.startswith("\n") else "\n") + tail.lstrip("\n")
    if updated == text:
        return None
    return updated


def refresh_cursor_memory(db: Session) -> None:
    """Patch the owner's standing note in place. Leave the rest of the note alone."""
    user = db.scalar(select(User).where(func.lower(User.email) == OWNER_EMAIL))
    if user is None or is_locked(user):
        return
    row = get_row(db, user.id)
    if row is None or not (row.markdown or "").strip():
        return
    updated = apply_cursor_memory_fix(row.markdown)
    if updated is None:
        return
    row.markdown = updated
    row.updated_at = datetime.now(timezone.utc)
    db.flush()


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
