from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import GrokConversation, GrokMessage, User
from app.services.demo_lock import is_locked

TITLE_MAX = 80


def should_persist(user: User) -> bool:
    return not is_locked(user)


def title_from_user_line(content: str) -> str:
    line = (content or "").strip().split("\n", 1)[0].strip()
    if not line:
        return "New chat"
    one_line = " ".join(line.split())
    if len(one_line) <= TITLE_MAX:
        return one_line
    return one_line[: TITLE_MAX - 1].rstrip() + "…"


def owned_conversation(db: Session, user: User, conversation_id: UUID) -> GrokConversation:
    row = db.scalar(
        select(GrokConversation).where(
            GrokConversation.id == conversation_id,
            GrokConversation.user_id == user.id,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return row


def list_conversations(db: Session, user: User) -> list[GrokConversation]:
    return list(
        db.scalars(
            select(GrokConversation)
            .where(GrokConversation.user_id == user.id)
            .order_by(GrokConversation.updated_at.desc())
        ).all()
    )


def get_conversation(db: Session, user: User, conversation_id: UUID) -> GrokConversation:
    row = owned_conversation(db, user, conversation_id)
    _ = row.messages
    return row


def create_conversation(db: Session, user: User, *, pane: str | None = None) -> GrokConversation:
    row = GrokConversation(user_id=user.id, title="New chat", pane=pane)
    db.add(row)
    db.flush()
    return row


def append_message(
    db: Session,
    conversation: GrokConversation,
    *,
    role: str,
    content: str,
    set_title_from_user: bool = False,
) -> GrokMessage:
    message = GrokMessage(conversation_id=conversation.id, role=role, content=content)
    db.add(message)
    now = datetime.now(timezone.utc)
    conversation.updated_at = now
    if set_title_from_user and role == "user":
        conversation.title = title_from_user_line(content)
    db.add(conversation)
    db.flush()
    return message


def patch_conversation_title(db: Session, user: User, conversation_id: UUID, title: str) -> GrokConversation:
    row = owned_conversation(db, user, conversation_id)
    cleaned = (title or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Title cannot be empty.")
    row.title = cleaned[:TITLE_MAX]
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.flush()
    return row


def delete_conversation(db: Session, user: User, conversation_id: UUID) -> None:
    row = owned_conversation(db, user, conversation_id)
    db.delete(row)


def conversation_history(db: Session, conversation_id: UUID) -> list[dict[str, str]]:
    rows = db.scalars(
        select(GrokMessage)
        .where(GrokMessage.conversation_id == conversation_id)
        .order_by(GrokMessage.created_at.asc())
    ).all()
    return [{"role": row.role, "content": row.content} for row in rows]
