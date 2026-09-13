from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.routers.articles import _owned_article
from app.schemas import GrokConversationDetailOut, GrokConversationOut, GrokConversationPatchIn, GrokMessageOut
from app.services import chat as chat_service
from app.services import grok_conversations as grok_store
from app.services.demo_lock import is_locked, reject_locked

router = APIRouter(tags=["chat"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: UUID | None = None
    article_id: UUID | None = None
    include_article: bool = False


@router.get("/chat")
def chat_status(user: User = Depends(get_current_user)) -> dict:
    locked = is_locked(user)
    return {
        "enabled": chat_service.key_configured() and not locked,
        "locked": locked,
        "provider": "xai",
        "model": (settings.xai_chat_model or "grok-4").strip(),
        "requests_per_hour": int(settings.chat_requests_per_hour or 120),
        "persist": grok_store.should_persist(user),
    }


@router.get("/chat/conversations", response_model=list[GrokConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[GrokConversationOut]:
    if not grok_store.should_persist(user):
        return []
    rows = grok_store.list_conversations(db, user)
    return [GrokConversationOut.model_validate(row) for row in rows]


@router.get("/chat/conversations/{conversation_id}", response_model=GrokConversationDetailOut)
def get_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GrokConversationDetailOut:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    row = grok_store.get_conversation(db, user, conversation_id)
    return GrokConversationDetailOut(
        id=row.id,
        title=row.title,
        pane=row.pane,
        created_at=row.created_at,
        updated_at=row.updated_at,
        messages=[GrokMessageOut.model_validate(item) for item in row.messages],
    )


@router.patch("/chat/conversations/{conversation_id}", response_model=GrokConversationOut)
def patch_conversation(
    conversation_id: UUID,
    payload: GrokConversationPatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GrokConversationOut:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    row = grok_store.patch_conversation_title(db, user, conversation_id, payload.title)
    db.commit()
    db.refresh(row)
    return GrokConversationOut.model_validate(row)


@router.delete("/chat/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    grok_store.delete_conversation(db, user, conversation_id)
    db.commit()
    return {"ok": True}


@router.post("/chat")
def chat(
    payload: ChatIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    reject_locked(user)
    chat_service.require_key()
    chat_service.enforce_rate_limit(user.id)

    persist = grok_store.should_persist(user)
    conversation_id = payload.conversation_id
    user_message_id: UUID | None = None
    assistant_message_id: UUID | None = None

    if persist:
        if conversation_id:
            conversation = grok_store.owned_conversation(db, user, conversation_id)
        else:
            conversation = grok_store.create_conversation(db, user)
            conversation_id = conversation.id
        is_first = not conversation.messages
        user_row = grok_store.append_message(
            db,
            conversation,
            role="user",
            content=payload.message.strip(),
            set_title_from_user=is_first,
        )
        user_message_id = user_row.id
        db.commit()
        history = grok_store.conversation_history(db, conversation_id)
    else:
        history = [{"role": "user", "content": payload.message.strip()}]

    history_for_xai = chat_service.validate_payload(chat_service.thread_window(history))
    excerpt = None
    include_article = bool(payload.include_article)
    if include_article:
        if not payload.article_id:
            raise HTTPException(status_code=400, detail="Open an article before attaching it to chat.")
        article = _owned_article(db, user, payload.article_id)
        excerpt = chat_service.article_excerpt(article)

    def events():
        assistant_parts: list[str] = []
        try:
            if persist and conversation_id and user_message_id:
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "conversation_id": str(conversation_id),
                            "user_message_id": str(user_message_id),
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
            for piece in chat_service.stream_completion(history_for_xai, excerpt, include_article=include_article):
                assistant_parts.append(piece)
                yield f"data: {json.dumps({'delta': piece}, ensure_ascii=False)}\n\n"
            if persist and conversation_id:
                assistant_text = "".join(assistant_parts).strip() or "Grok did not return a reply."
                conversation = grok_store.owned_conversation(db, user, conversation_id)
                assistant_row = grok_store.append_message(
                    db,
                    conversation,
                    role="assistant",
                    content=assistant_text,
                )
                db.commit()
                assistant_message_id = assistant_row.id
                yield (
                    "data: "
                    + json.dumps(
                        {
                            "conversation_id": str(conversation_id),
                            "assistant_message_id": str(assistant_message_id),
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
            yield "data: [DONE]\n\n"
        except HTTPException as exc:
            db.rollback()
            detail = exc.detail if isinstance(exc.detail, str) else "Chat failed."
            yield f"data: {json.dumps({'error': detail})}\n\n"
        except Exception:
            db.rollback()
            yield f"data: {json.dumps({'error': 'Chat failed.'})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
