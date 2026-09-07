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
from app.services import chat as chat_service

router = APIRouter(tags=["chat"])


class ChatMessageIn(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=8000)


class ChatIn(BaseModel):
    messages: list[ChatMessageIn] = Field(min_length=1, max_length=24)
    article_id: UUID | None = None
    include_article: bool = False


@router.get("/chat")
def chat_status(user: User = Depends(get_current_user)) -> dict:
    _ = user
    return {
        "enabled": chat_service.key_configured(),
        "provider": "xai",
        "model": (settings.xai_chat_model or "grok-4").strip(),
        "requests_per_hour": int(settings.chat_requests_per_hour or 30),
    }


@router.post("/chat")
def chat(
    payload: ChatIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    history = chat_service.validate_payload([item.model_dump() for item in payload.messages])
    chat_service.enforce_rate_limit(user.id)
    excerpt = None
    if payload.include_article:
        if not payload.article_id:
            raise HTTPException(status_code=400, detail="Open an article before attaching it to chat.")
        article = _owned_article(db, user, payload.article_id)
        excerpt = chat_service.article_excerpt(article)

    def events():
        try:
            for piece in chat_service.stream_completion(history, excerpt):
                yield f"data: {json.dumps({'delta': piece}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else "Chat failed."
            yield f"data: {json.dumps({'error': detail})}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
