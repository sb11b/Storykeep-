from __future__ import annotations

import asyncio
import logging
import time
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.deps import get_current_user
from app.models import User
from app.routers.articles import _owned_article
from app.schemas import GrokConversationDetailOut, GrokConversationOut, GrokConversationPatchIn, GrokMessageFileOut, GrokMessageOut
from app.services import chat as chat_service
from app.services import chat_attachments
from app.services import grok_conversations as grok_store
from app.services.demo_lock import is_locked, reject_locked

router = APIRouter(tags=["chat"])


class ChatIn(BaseModel):
    message: str = Field(default="", max_length=8000)
    conversation_id: UUID | None = None
    model: str | None = None
    article_id: UUID | None = None
    include_article: bool = False
    recap_question: bool = False
    retry: bool = False
    media_ids: list[UUID] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def require_text_or_files(self) -> "ChatIn":
        if self.retry:
            return self
        if not self.message.strip() and not self.media_ids:
            raise ValueError("Type a message or attach a file.")
        return self


def _file_out(row) -> GrokMessageFileOut:
    return GrokMessageFileOut(
        media_id=row.media_id,
        filename=row.filename,
        content_type=row.content_type,
        kind=row.kind,
        url=f"/api/v1/media/{row.media_id}",
        byte_size=row.byte_size,
    )


def _message_out(row) -> GrokMessageOut:
    return GrokMessageOut(
        id=row.id,
        role=row.role,
        content=row.content,
        created_at=row.created_at,
        files=[_file_out(item) for item in (row.files or [])],
    )


def _conversation_out(row) -> GrokConversationOut:
    return GrokConversationOut.model_validate(row)


def _conversation_detail(row) -> GrokConversationDetailOut:
    return GrokConversationDetailOut(
        id=row.id,
        title=row.title,
        pane=row.pane,
        model=row.model or chat_service.MODEL_AUTO,
        last_model=row.last_model,
        recap_question=bool(row.recap_question),
        created_at=row.created_at,
        updated_at=row.updated_at,
        messages=[_message_out(item) for item in row.messages],
    )


@router.get("/chat")
def chat_status(user: User = Depends(get_current_user)) -> dict:
    locked = is_locked(user)
    models = chat_service.available_models()
    return {
        "enabled": chat_service.key_configured() and not locked,
        "locked": locked,
        "provider": "xai",
        "model": chat_service.default_full_model(),
        "models": models,
        "default_model": chat_service.default_full_model(),
        "fast_model": chat_service.default_fast_model(),
        "requests_per_hour": int(settings.chat_requests_per_hour or 120),
        "persist": grok_store.should_persist(user),
        "key_configured": chat_service.key_configured(),
        "key_format_ok": chat_service.key_format_ok(),
    }


@router.get("/chat/health")
def chat_health(user: User = Depends(get_current_user)) -> dict:
    """Ping xAI with a 1-token request. Auth required; does not consume chat quota."""
    if not chat_service.key_configured():
        return {
            "ok": False,
            "model": chat_service.default_fast_model(),
            "ms": 0,
            "xai_status": None,
            "message": "XAI_API_KEY is not set or must start with xai-.",
        }
    return chat_service.ping_xai()


@router.get("/chat/conversations", response_model=list[GrokConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[GrokConversationOut]:
    if not grok_store.should_persist(user):
        return []
    rows = grok_store.list_conversations(db, user)
    return [_conversation_out(row) for row in rows]


@router.get("/chat/conversations/{conversation_id}", response_model=GrokConversationDetailOut)
def get_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GrokConversationDetailOut:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    row = grok_store.get_conversation(db, user, conversation_id)
    return _conversation_detail(row)


@router.patch("/chat/conversations/{conversation_id}", response_model=GrokConversationOut)
def patch_conversation(
    conversation_id: UUID,
    payload: GrokConversationPatchIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GrokConversationOut:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    fields = payload.model_fields_set
    model_value = chat_service.normalize_model_choice(payload.model) if "model" in fields else None
    row = grok_store.patch_conversation(
        db,
        user,
        conversation_id,
        title=payload.title,
        model=model_value,
        recap_question=payload.recap_question,
        title_provided="title" in fields,
        model_provided="model" in fields,
        recap_provided="recap_question" in fields,
    )
    db.commit()
    db.refresh(row)
    return _conversation_out(row)


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
async def chat(
    payload: ChatIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    reject_locked(user)
    chat_service.require_key()
    user_id = user.id
    chat_service.enforce_rate_limit(user_id)

    persist = grok_store.should_persist(user)
    conversation_id = payload.conversation_id
    user_message_id: UUID | None = None
    model_choice = chat_service.normalize_model_choice(payload.model) if payload.model else chat_service.MODEL_AUTO
    recap_question = bool(payload.recap_question)

    user_text = payload.message.strip()
    media_ids = list(payload.media_ids or [])
    current_files: list[dict] = []

    if persist:
        if payload.retry:
            if not conversation_id:
                raise HTTPException(status_code=400, detail="Open the thread you want to retry.")
            conversation = grok_store.owned_conversation(db, user, conversation_id)
            pending = grok_store.pending_user_turn(db, conversation_id)
            if not pending:
                raise HTTPException(status_code=400, detail="Nothing to retry on this thread.")
            grok_store.trim_trailing_assistants(db, conversation_id)
            user_text = pending.content.strip()
            user_message_id = pending.id
            current_files = [
                {
                    "media_id": item.media_id,
                    "filename": item.filename,
                    "content_type": item.content_type,
                    "kind": item.kind,
                    "extract_text": item.extract_text or "",
                    "byte_size": item.byte_size,
                    "url": f"/api/v1/media/{item.media_id}",
                }
                for item in (pending.files or [])
            ]
            model_choice = chat_service.normalize_model_choice(conversation.model or chat_service.MODEL_AUTO)
            if payload.model:
                model_choice = chat_service.normalize_model_choice(payload.model)
                conversation.model = model_choice
            conversation.recap_question = recap_question
            db.add(conversation)
            db.commit()
            history = grok_store.conversation_history(db, conversation_id)
        elif conversation_id:
            conversation = grok_store.owned_conversation(db, user, conversation_id)
            model_choice = chat_service.normalize_model_choice(conversation.model or chat_service.MODEL_AUTO)
            if payload.model:
                model_choice = chat_service.normalize_model_choice(payload.model)
                conversation.model = model_choice
            conversation.recap_question = recap_question
            db.add(conversation)
            is_first = not conversation.messages
            filenames = None
            if media_ids:
                preview = chat_attachments.preview_files(db, user, media_ids)
                filenames = [item["filename"] for item in preview]
            user_row = grok_store.append_message(
                db,
                conversation,
                role="user",
                content=user_text,
                set_title_from_user=is_first,
                title_filenames=filenames,
            )
            if media_ids:
                chat_attachments.attach_to_message(db, user, user_row, media_ids)
            user_message_id = user_row.id
            db.commit()
            history = grok_store.conversation_history(db, conversation_id)
        else:
            if payload.model:
                model_choice = chat_service.normalize_model_choice(payload.model)
            conversation = grok_store.create_conversation(db, user, model=model_choice)
            conversation.recap_question = recap_question
            db.add(conversation)
            conversation_id = conversation.id
            is_first = True
            filenames = None
            if media_ids:
                preview = chat_attachments.preview_files(db, user, media_ids)
                filenames = [item["filename"] for item in preview]
            user_row = grok_store.append_message(
                db,
                conversation,
                role="user",
                content=user_text,
                set_title_from_user=is_first,
                title_filenames=filenames,
            )
            if media_ids:
                chat_attachments.attach_to_message(db, user, user_row, media_ids)
            user_message_id = user_row.id
            db.commit()
            history = grok_store.conversation_history(db, conversation_id)
    else:
        if payload.model:
            model_choice = chat_service.normalize_model_choice(payload.model)
        current_files = chat_attachments.preview_files(db, user, media_ids) if media_ids else []
        history = [{"role": "user", "content": user_text, "files": current_files}]

    if history:
        current_files = history[-1].get("files") or current_files
    route_text = chat_attachments.merge_attachment_text(user_text, current_files, include_extracts=True)
    history_for_route = chat_service.drop_trailing_assistants(
        [{"role": item.get("role"), "content": item.get("content") or ""} for item in history]
    )
    history_window = chat_service.thread_window(history_for_route)
    resolved_model = chat_service.resolve_model_for_request(
        model_choice,
        route_text or user_text or "attached file",
        history_window,
    )
    prepared = chat_service.messages_for_xai(history, model=resolved_model, db=db, user=user)
    history_for_xai = chat_service.validate_payload(prepared)
    excerpt = None
    include_article = bool(payload.include_article)
    if include_article:
        if not payload.article_id:
            raise HTTPException(status_code=400, detail="Open an article before attaching it to chat.")
        article = _owned_article(db, user, payload.article_id)
        excerpt = chat_service.article_excerpt(article)
    has_attachments = any(item.get("files") for item in history)

    def _persist_assistant(text: str) -> str | None:
        cleaned = (text or "").strip()
        if not persist or not conversation_id or not cleaned:
            return None
        try:
            with SessionLocal() as stream_db:
                conversation = grok_store.owned_conversation_for_user(stream_db, user_id, conversation_id)
                assistant_row = grok_store.append_message(
                    stream_db,
                    conversation,
                    role="assistant",
                    content=cleaned,
                )
                grok_store.patch_conversation_for_user(
                    stream_db,
                    user_id,
                    conversation_id,
                    last_model=resolved_model,
                )
                stream_db.commit()
                return str(assistant_row.id)
        except Exception:
            logger.exception(
                "Failed to persist assistant reply user=%s conversation=%s",
                user_id,
                conversation_id,
            )
            return None

    async def events():
        assistant_parts: list[str] = []
        started = time.perf_counter()
        ttft_ms: int | None = None
        flushed = False

        def _log(reason: str) -> None:
            logger.info(
                "larry-chat ttft_ms=%s flushed=%s reason=%s model=%s user=%s conversation=%s chars=%s",
                ttft_ms if ttft_ms is not None else -1,
                flushed,
                reason,
                resolved_model,
                user_id,
                conversation_id,
                sum(len(part) for part in assistant_parts),
            )

        try:
            meta = {
                "conversation_id": str(conversation_id) if conversation_id else None,
                "user_message_id": str(user_message_id) if user_message_id else None,
                "model": resolved_model,
                "model_choice": model_choice,
            }
            if persist and conversation_id and user_message_id:
                yield chat_service.encode_sse({k: v for k, v in meta.items() if v is not None})
            elif not persist:
                yield chat_service.encode_sse({"model": resolved_model, "model_choice": model_choice})
            else:
                yield chat_service.encode_sse({"model": resolved_model, "model_choice": model_choice})
            yield chat_service.SSE_PADDING
            await asyncio.sleep(0)
            async for piece in chat_service.stream_completion(
                history_for_xai,
                excerpt,
                include_article=include_article,
                recap_question=recap_question,
                model=resolved_model,
                model_choice=model_choice,
                user_id=user_id,
                has_attachments=has_attachments,
            ):
                if await request.is_disconnected():
                    _log("aborted")
                    _persist_assistant("".join(assistant_parts))
                    return
                assistant_parts.append(piece)
                if ttft_ms is None:
                    ttft_ms = int((time.perf_counter() - started) * 1000)
                flushed = True
                yield chat_service.encode_sse({"delta": piece})
                await asyncio.sleep(0)
            if persist and conversation_id:
                assistant_text = "".join(assistant_parts).strip() or "No reply came back."
                assistant_message_id = _persist_assistant(assistant_text)
                if assistant_message_id:
                    yield chat_service.encode_sse(
                        {
                            "conversation_id": str(conversation_id),
                            "assistant_message_id": assistant_message_id,
                            "model": resolved_model,
                            "model_choice": model_choice,
                        }
                    )
            yield chat_service.encode_sse("[DONE]")
            _log("done")
        except HTTPException as exc:
            status_code, detail = chat_service.http_exception_detail(exc)
            partial_text = "".join(assistant_parts)
            flushed = flushed or bool(partial_text)
            _log(f"http-{status_code}")
            saved_id = _persist_assistant(partial_text) if persist else None
            if saved_id and conversation_id:
                yield chat_service.encode_sse(
                    {
                        "conversation_id": str(conversation_id),
                        "assistant_message_id": saved_id,
                        "model": resolved_model,
                        "model_choice": model_choice,
                        "partial": True,
                    }
                )
            yield chat_service.encode_sse(
                chat_service.stream_error_event(status_code, detail, partial=bool(partial_text))
            )
        except asyncio.CancelledError:
            partial_text = "".join(assistant_parts)
            flushed = flushed or bool(partial_text)
            _log("cancelled")
            _persist_assistant(partial_text)
            raise
        except Exception as exc:
            partial_text = "".join(assistant_parts)
            flushed = flushed or bool(partial_text)
            logger.exception(
                "Chat stream unexpected error user=%s conversation=%s partial_chars=%s",
                user_id,
                conversation_id,
                len(partial_text),
            )
            _log("error")
            saved_id = _persist_assistant(partial_text) if persist else None
            if saved_id and conversation_id:
                yield chat_service.encode_sse(
                    {
                        "conversation_id": str(conversation_id),
                        "assistant_message_id": saved_id,
                        "partial": True,
                    }
                )
            yield chat_service.encode_sse(
                chat_service.stream_error_event(500, str(exc) or exc.__class__.__name__, partial=bool(partial_text))
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Encoding": "identity",
        },
    )
