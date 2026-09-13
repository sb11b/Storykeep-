from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import GrokConversation, GrokMessage, User
from app.services.demo_lock import is_locked

TITLE_MAX = 80


def should_persist(user: User) -> bool:
    return not is_locked(user)


def title_from_user_line(content: str, filenames: list[str] | None = None) -> str:
    line = (content or "").strip().split("\n", 1)[0].strip()
    if not line and filenames:
        line = (filenames[0] or "").strip()
    if not line:
        return "New chat"
    one_line = " ".join(line.split())
    if len(one_line) <= TITLE_MAX:
        return one_line
    return one_line[: TITLE_MAX - 1].rstrip() + "…"


def owned_conversation(db: Session, user: User, conversation_id: UUID) -> GrokConversation:
    return owned_conversation_for_user(db, user.id, conversation_id)


def owned_conversation_for_user(db: Session, user_id: UUID, conversation_id: UUID) -> GrokConversation:
    row = db.scalar(
        select(GrokConversation).where(
            GrokConversation.id == conversation_id,
            GrokConversation.user_id == user_id,
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
    row = db.scalar(
        select(GrokConversation)
        .options(selectinload(GrokConversation.messages).selectinload(GrokMessage.files))
        .where(GrokConversation.id == conversation_id, GrokConversation.user_id == user.id)
    )
    if not row:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return row


def create_conversation(
    db: Session,
    user: User,
    *,
    pane: str | None = None,
    model: str = "auto",
    reasoning: str = "auto",
) -> GrokConversation:
    row = GrokConversation(user_id=user.id, title="New chat", pane=pane, model=model, reasoning=reasoning)
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
    title_filenames: list[str] | None = None,
    created_at: datetime | None = None,
) -> GrokMessage:
    stamp = created_at or datetime.now(timezone.utc)
    message = GrokMessage(
        conversation_id=conversation.id,
        role=role,
        content=content,
        created_at=stamp,
    )
    db.add(message)
    conversation.updated_at = stamp
    if set_title_from_user and role == "user":
        conversation.title = title_from_user_line(content, title_filenames)
    db.add(conversation)
    db.flush()
    return message


def first_user_message_content(db: Session, conversation_id: UUID) -> str | None:
    row = db.scalar(
        select(GrokMessage)
        .where(GrokMessage.conversation_id == conversation_id, GrokMessage.role == "user")
        .order_by(GrokMessage.created_at.asc(), GrokMessage.id.asc())
        .limit(1)
    )
    if not row:
        return None
    return row.content


def resolve_patched_title(proposed: str, first_user_content: str | None) -> str:
    cleaned = (proposed or "").strip()
    if cleaned:
        return cleaned[:TITLE_MAX]
    if first_user_content:
        return title_from_user_line(first_user_content)
    return "New chat"


def patch_conversation(
    db: Session,
    user: User,
    conversation_id: UUID,
    *,
    title: str | None = None,
    model: str | None = None,
    last_model: str | None = None,
    reasoning: str | None = None,
    last_reasoning: str | None = None,
    recap_question: bool | None = None,
    saved_note_id: UUID | None = None,
    title_provided: bool = False,
    model_provided: bool = False,
    reasoning_provided: bool = False,
    recap_provided: bool = False,
    saved_note_provided: bool = False,
) -> GrokConversation:
    return patch_conversation_for_user(
        db,
        user.id,
        conversation_id,
        title=title,
        model=model,
        last_model=last_model,
        reasoning=reasoning,
        last_reasoning=last_reasoning,
        recap_question=recap_question,
        saved_note_id=saved_note_id,
        title_provided=title_provided,
        model_provided=model_provided,
        reasoning_provided=reasoning_provided,
        recap_provided=recap_provided,
        saved_note_provided=saved_note_provided,
    )


def patch_conversation_for_user(
    db: Session,
    user_id: UUID,
    conversation_id: UUID,
    *,
    title: str | None = None,
    model: str | None = None,
    last_model: str | None = None,
    reasoning: str | None = None,
    last_reasoning: str | None = None,
    recap_question: bool | None = None,
    saved_note_id: UUID | None = None,
    title_provided: bool = False,
    model_provided: bool = False,
    reasoning_provided: bool = False,
    recap_provided: bool = False,
    saved_note_provided: bool = False,
) -> GrokConversation:
    row = owned_conversation_for_user(db, user_id, conversation_id)
    if title_provided:
        first_user = first_user_message_content(db, conversation_id)
        row.title = resolve_patched_title(title or "", first_user)
    if model_provided and model is not None:
        row.model = model
    if reasoning_provided and reasoning is not None:
        row.reasoning = reasoning
    if recap_provided and recap_question is not None:
        row.recap_question = recap_question
    if saved_note_provided:
        row.saved_note_id = saved_note_id
    if last_model is not None:
        row.last_model = last_model
    if last_reasoning is not None:
        row.last_reasoning = last_reasoning
    row.updated_at = datetime.now(timezone.utc)
    db.add(row)
    db.flush()
    return row


def patch_conversation_title(db: Session, user: User, conversation_id: UUID, title: str) -> GrokConversation:
    return patch_conversation(db, user, conversation_id, title=title, title_provided=True)


def delete_conversation(db: Session, user: User, conversation_id: UUID) -> None:
    row = owned_conversation(db, user, conversation_id)
    db.delete(row)


def conversation_history(db: Session, conversation_id: UUID) -> list[dict]:
    rows = list(
        db.scalars(
            select(GrokMessage)
            .options(selectinload(GrokMessage.files))
            .where(GrokMessage.conversation_id == conversation_id)
            .order_by(GrokMessage.created_at.asc(), GrokMessage.id.asc())
        ).all()
    )
    return [
        {
            "role": row.role,
            "content": row.content,
            "files": [
                {
                    "media_id": item.media_id,
                    "filename": item.filename,
                    "content_type": item.content_type,
                    "kind": item.kind,
                    "extract_text": item.extract_text or "",
                    "byte_size": item.byte_size,
                    "url": f"/api/v1/media/{item.media_id}",
                }
                for item in (row.files or [])
            ],
        }
        for row in rows
    ]


def pending_user_turn(db: Session, conversation_id: UUID) -> GrokMessage | None:
    rows = list(
        db.scalars(
            select(GrokMessage)
            .options(selectinload(GrokMessage.files))
            .where(GrokMessage.conversation_id == conversation_id)
            .order_by(GrokMessage.created_at.asc(), GrokMessage.id.asc())
        ).all()
    )
    for row in reversed(rows):
        if row.role == "user":
            return row
    return None


def trim_trailing_assistants(db: Session, conversation_id: UUID) -> None:
    rows = list(
        db.scalars(
            select(GrokMessage)
            .where(GrokMessage.conversation_id == conversation_id)
            .order_by(GrokMessage.created_at.asc(), GrokMessage.id.asc())
        ).all()
    )
    changed = False
    for row in reversed(rows):
        if row.role != "assistant":
            break
        db.delete(row)
        changed = True
    if changed:
        db.flush()
