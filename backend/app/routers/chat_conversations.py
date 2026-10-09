from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.routers.chat import _message_out
from app.schemas import GrokConversationDetailOut, GrokConversationOut, GrokConversationPatchIn
from app.services import chat as chat_service
from app.services import grok_conversations as grok_store
from app.services import message_crypto

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat/conversations", tags=["chat"])


class ConversationCreateIn(BaseModel):
    id: UUID | None = None
    model: str | None = Field(default=None, max_length=64)
    reasoning: str | None = Field(default=None, max_length=16)
    pane: str | None = Field(default=None, max_length=80)


def _conversation_out(row) -> GrokConversationOut:
    return GrokConversationOut.model_validate(row)


def _conversation_detail(row, *, crypto_enabled: bool = False) -> GrokConversationDetailOut:
    return GrokConversationDetailOut(
        id=row.id,
        title=row.title,
        pane=row.pane,
        model=row.model or chat_service.MODEL_AUTO,
        last_model=row.last_model,
        reasoning=getattr(row, "reasoning", None) or chat_service.REASONING_AUTO,
        last_reasoning=getattr(row, "last_reasoning", None),
        recap_question=bool(row.recap_question),
        saved_note_id=getattr(row, "saved_note_id", None),
        pinned=bool(getattr(row, "pinned", False)),
        pinned_at=getattr(row, "pinned_at", None),
        created_at=row.created_at,
        updated_at=row.updated_at,
        messages=[_message_out(item, crypto_enabled=crypto_enabled) for item in row.messages],
    )


@router.get("", response_model=list[GrokConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[GrokConversationOut]:
    if not grok_store.should_persist(user):
        return []
    rows = grok_store.list_conversations(db, user)
    return [_conversation_out(row) for row in rows]


@router.post("", response_model=GrokConversationOut, status_code=201)
def create_conversation(
    payload: ConversationCreateIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> GrokConversationOut:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    body = payload or ConversationCreateIn()
    model_choice = chat_service.normalize_model_choice(body.model) if body.model else chat_service.MODEL_AUTO
    reasoning_choice = (
        chat_service.normalize_reasoning_effort(body.reasoning)
        if body.reasoning is not None
        else chat_service.REASONING_AUTO
    )
    stored_reasoning = (
        chat_service.REASONING_AUTO if model_choice == chat_service.MODEL_AUTO else reasoning_choice
    )
    row = grok_store.create_conversation(
        db,
        user,
        pane=body.pane,
        model=model_choice,
        reasoning=stored_reasoning,
        conversation_id=body.id,
    )
    db.commit()
    db.refresh(row)
    logger.info("chat conversation created user=%s id=%s", user.id, row.id)
    return _conversation_out(row)


@router.get("/{conversation_id}", response_model=GrokConversationDetailOut)
def get_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> GrokConversationDetailOut:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    row = grok_store.get_conversation(db, user, conversation_id)
    return _conversation_detail(row, crypto_enabled=message_crypto.is_enabled(user))


@router.patch("/{conversation_id}", response_model=GrokConversationOut)
def patch_conversation(
    conversation_id: UUID,
    payload: GrokConversationPatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> GrokConversationOut:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    fields = payload.model_fields_set
    model_value = chat_service.normalize_model_choice(payload.model) if "model" in fields else None
    reasoning_value = (
        chat_service.normalize_reasoning_effort(payload.reasoning) if "reasoning" in fields else None
    )
    row = grok_store.patch_conversation(
        db,
        user,
        conversation_id,
        title=payload.title,
        model=model_value,
        reasoning=reasoning_value,
        recap_question=payload.recap_question,
        saved_note_id=payload.saved_note_id,
        pinned=payload.pinned,
        title_provided="title" in fields,
        model_provided="model" in fields,
        reasoning_provided="reasoning" in fields,
        recap_provided="recap_question" in fields,
        saved_note_provided="saved_note_id" in fields,
        pinned_provided="pinned" in fields,
    )
    db.commit()
    db.refresh(row)
    return _conversation_out(row)


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict[str, bool]:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    grok_store.delete_conversation(db, user, conversation_id)
    db.commit()
    return {"ok": True}
