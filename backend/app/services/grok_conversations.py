from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import GrokConversation, GrokMessage, User
from app.services.demo_lock import is_locked
from app.services import message_crypto

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
            .order_by(
                GrokConversation.pinned.desc(),
                GrokConversation.pinned_at.desc().nulls_last(),
                GrokConversation.updated_at.desc(),
            )
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


def owned_assistant_message(db: Session, user: User, message_id: UUID) -> GrokMessage:
    row = db.scalar(
        select(GrokMessage)
        .join(GrokConversation, GrokMessage.conversation_id == GrokConversation.id)
        .where(
            GrokMessage.id == message_id,
            GrokConversation.user_id == user.id,
        )
    )
    if not row or row.role != "assistant":
        raise HTTPException(status_code=404, detail="Message not found.")
    return row


def lookup_owned_conversation(db: Session, user: User, conversation_id: UUID) -> GrokConversation | None:
    return db.scalar(
        select(GrokConversation).where(
            GrokConversation.id == conversation_id,
            GrokConversation.user_id == user.id,
        )
    )


def create_conversation(
    db: Session,
    user: User,
    *,
    pane: str | None = None,
    model: str = "auto",
    reasoning: str = "auto",
    conversation_id: UUID | None = None,
) -> GrokConversation:
    if conversation_id is not None:
        existing = lookup_owned_conversation(db, user, conversation_id)
        if existing:
            return existing
    kwargs: dict = {
        "user_id": user.id,
        "title": "New chat",
        "pane": pane,
        "model": model,
        "reasoning": reasoning,
    }
    if conversation_id is not None:
        kwargs["id"] = conversation_id
    row = GrokConversation(**kwargs)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        raced = lookup_owned_conversation(db, user, conversation_id) if conversation_id is not None else None
        if raced:
            return raced
        raise
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
        encrypted=False,
        created_at=stamp,
    )
    db.add(message)
    conversation.updated_at = stamp
    if set_title_from_user and role == "user":
        conversation.title = title_from_user_line(content, title_filenames)
    db.add(conversation)
    db.flush()
    return message


def append_encrypted_message(
    db: Session,
    conversation: GrokConversation,
    *,
    role: str,
    iv: str,
    ct: str,
    message_id: UUID | None = None,
    title: str | None = None,
    created_at: datetime | None = None,
) -> GrokMessage:
    message_crypto.validate_ciphertext(iv, ct)
    stamp = created_at or datetime.now(timezone.utc)
    kwargs: dict = {
        "conversation_id": conversation.id,
        "role": role,
        "content": None,
        "body_iv": iv.strip(),
        "body_ct": ct.strip(),
        "encrypted": True,
        "created_at": stamp,
    }
    if message_id is not None:
        kwargs["id"] = message_id
    message = GrokMessage(**kwargs)
    db.add(message)
    conversation.updated_at = stamp
    if title and role == "user":
        cleaned = (title or "").strip()[:TITLE_MAX]
        if cleaned:
            conversation.title = cleaned
    db.add(conversation)
    db.flush()
    return message


def migrate_message_to_encrypted(
    db: Session,
    user_id: UUID,
    message_id: UUID,
    *,
    iv: str,
    ct: str,
) -> GrokMessage:
    row = db.scalar(
        select(GrokMessage)
        .join(GrokConversation, GrokMessage.conversation_id == GrokConversation.id)
        .where(
            GrokMessage.id == message_id,
            GrokConversation.user_id == user_id,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="Message not found.")
    if row.encrypted:
        return row
    message_crypto.validate_ciphertext(iv, ct)
    row.content = None
    row.body_iv = iv.strip()
    row.body_ct = ct.strip()
    row.encrypted = True
    db.add(row)
    db.flush()
    return row


def last_message_content(db: Session, conversation_id: UUID) -> str | None:
    row = db.scalar(
        select(GrokMessage)
        .where(GrokMessage.conversation_id == conversation_id)
        .order_by(GrokMessage.created_at.desc(), GrokMessage.id.desc())
        .limit(1)
    )
    if not row:
        return None
    if row.encrypted:
        return None
    return row.content


def message_count(db: Session, conversation_id: UUID) -> int:
    return int(
        db.scalar(select(func.count()).select_from(GrokMessage).where(GrokMessage.conversation_id == conversation_id))
        or 0
    )


def first_user_message_content(db: Session, conversation_id: UUID) -> str | None:
    row = db.scalar(
        select(GrokMessage)
        .where(GrokMessage.conversation_id == conversation_id, GrokMessage.role == "user")
        .order_by(GrokMessage.created_at.asc(), GrokMessage.id.asc())
        .limit(1)
    )
    if not row:
        return None
    if row.encrypted:
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
    pinned: bool | None = None,
    title_provided: bool = False,
    model_provided: bool = False,
    reasoning_provided: bool = False,
    recap_provided: bool = False,
    saved_note_provided: bool = False,
    pinned_provided: bool = False,
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
        pinned=pinned,
        title_provided=title_provided,
        model_provided=model_provided,
        reasoning_provided=reasoning_provided,
        recap_provided=recap_provided,
        saved_note_provided=saved_note_provided,
        pinned_provided=pinned_provided,
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
    pinned: bool | None = None,
    title_provided: bool = False,
    model_provided: bool = False,
    reasoning_provided: bool = False,
    recap_provided: bool = False,
    saved_note_provided: bool = False,
    pinned_provided: bool = False,
) -> GrokConversation:
    row = owned_conversation_for_user(db, user_id, conversation_id)
    touch_time = False
    if title_provided:
        first_user = first_user_message_content(db, conversation_id)
        row.title = resolve_patched_title(title or "", first_user)
        touch_time = True
    if model_provided and model is not None:
        row.model = model
        touch_time = True
    if reasoning_provided and reasoning is not None:
        row.reasoning = reasoning
        touch_time = True
    if recap_provided and recap_question is not None:
        row.recap_question = recap_question
        touch_time = True
    if saved_note_provided:
        row.saved_note_id = saved_note_id
        touch_time = True
    if pinned_provided and pinned is not None:
        row.pinned = pinned
        row.pinned_at = datetime.now(timezone.utc) if pinned else None
    if last_model is not None:
        row.last_model = last_model
        touch_time = True
    if last_reasoning is not None:
        row.last_reasoning = last_reasoning
        touch_time = True
    if touch_time:
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
    out: list[dict] = []
    for row in rows:
        if row.encrypted:
            continue
        out.append(
            {
                "role": row.role,
                "content": row.content or "",
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
        )
    return out


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
