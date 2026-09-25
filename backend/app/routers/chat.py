from __future__ import annotations

import asyncio
import logging
import time
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.deps import require_user
from app.models import User
from app.routers.articles import _owned_article
from app.services.destination import is_composed_guid
from app.schemas import GrokConversationDetailOut, GrokConversationOut, GrokConversationPatchIn, GrokMessageFileOut, GrokMessageOut
from app.http_limits import log_chat_exception
from app.services import chat as chat_service
from app.services import chat_attachments
from app.services import chat_image
from app.services import chat_docx
from app.services import calendar_access as calendars
from app.services.calendar_tool import (
    ADD_EVENT_TOOL,
    CALENDAR_OFF_APPEND,
    CALENDAR_ON_APPEND,
    assemble_tool_calls,
    extract_calendar_proposal,
)
from app.services import grok_conversations as grok_store
from app.services import imagine as imagine_service
from app.services import junior_memory
from app.services import mail as mail_service
from app.services import mail_tool
from app.services import fastmail_jmap as jmap
from app.services.demo_lock import is_locked
from app.services.include_chunk import WORKING_NOTE_CHAR_CAP
from app.services.include_chunk import format_excerpt as format_include_excerpt
from app.services.include_chunk import resolve_include_slice
from app.services.include_chunk import slice_id_from_meta
from app.services.include_chunk import slice_meta as include_slice_meta
from app.services.working_note import heading_from_instruction
from app.services.junior_jobs import (
    UNREAD_READER_SYSTEM,
    attach_unread_catalog,
    news_summary_reply,
    unread_news_block,
    wants_news_summary,
)
from app.services import web_search as search_tool
from app.services import railway_tool
from app.services import github_tool
from app.services import cursor_agent_tool
from app.services import chat_index
from app.services import message_crypto
from app.services import tts as tts_service

router = APIRouter(tags=["chat"])


class HistoryTurn(BaseModel):
    role: str = Field(max_length=16)
    content: str = Field(max_length=100_000)


class ChatIn(BaseModel):
    message: str = Field(default="", max_length=100_000)
    conversation_id: UUID | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    article_id: UUID | None = None
    include_article: bool = False
    include_note_id: UUID | None = None
    working_note_id: UUID | None = None
    include_mode: str | None = None
    include_selection: str | None = Field(default=None, max_length=12_000)
    include_heading: str | None = Field(default=None, max_length=400)
    include_offset: int = 0
    recap_question: bool = False
    retry: bool = False
    media_ids: list[UUID] = Field(default_factory=list, max_length=5)
    history_override: list[HistoryTurn] | None = None
    client_title: str | None = Field(default=None, max_length=80)
    pane_name: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def require_text_or_files(self) -> "ChatIn":
        if self.retry:
            return self
        if not self.message.strip() and not self.media_ids:
            raise ValueError("Type a message or attach a file.")
        return self


class ConversationCreateIn(BaseModel):
    id: UUID | None = None
    model: str | None = Field(default=None, max_length=64)
    reasoning: str | None = Field(default=None, max_length=16)
    pane: str | None = Field(default=None, max_length=80)


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=search_tool.QUERY_CHAR_CAP)


@router.post("/search")
def junior_web_search(payload: SearchIn, user: User = Depends(require_user)) -> dict:
    search_tool.reject_demo(user)
    outcome = search_tool.search(payload.query)
    if outcome.fatal:
        raise HTTPException(status_code=outcome.status_code or 503, detail=outcome.detail)
    return outcome.as_payload()


class ImagineIn(BaseModel):
    prompt: str = Field(default="", max_length=4000)
    conversation_id: UUID | None = None
    media_ids: list[UUID] = Field(default_factory=list, max_length=5)


def _file_out(row) -> GrokMessageFileOut:
    return GrokMessageFileOut(
        media_id=row.media_id,
        filename=row.filename,
        content_type=row.content_type,
        kind=row.kind,
        url=f"/api/v1/media/{row.media_id}",
        byte_size=row.byte_size,
        extract_text=getattr(row, "extract_text", None) or None,
    )


def _message_out(row, *, crypto_enabled: bool = False) -> GrokMessageOut:
    body = message_crypto.message_body_out(row, crypto_enabled=crypto_enabled)
    return GrokMessageOut(
        id=row.id,
        role=row.role,
        content=body.get("content"),
        iv=body.get("iv"),
        ct=body.get("ct"),
        encrypted=bool(body.get("encrypted")),
        created_at=row.created_at,
        files=[_file_out(item) for item in (row.files or [])],
    )


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


@router.get("/chat")
def chat_status(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
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
        "reasoning_efforts": list(chat_service.REASONING_EFFORTS),
        "requests_per_hour": int(settings.chat_requests_per_hour or 120),
        "imagine_requests_per_hour": int(settings.imagine_requests_per_hour or 10),
        "persist": grok_store.should_persist(user),
        "key_configured": chat_service.key_configured(),
        "key_format_ok": chat_service.key_format_ok(),
        "message_crypto": message_crypto.status(db, user),
    }


@router.get("/chat/health")
def chat_health(user: User = Depends(require_user)) -> dict:
    """Ping xAI with a 1-token request. Auth required; does not consume chat quota."""
    if not chat_service.key_configured():
        return {
            "ok": False,
            "model": chat_service.default_full_model(),
            "reasoning": chat_service.DEFAULT_REASONING_EFFORT,
            "ttft_ms": None,
            "xai_status": None,
            "message": "XAI_API_KEY is not set or must start with xai-.",
        }
    return chat_service.ping_xai()


@router.get("/chat/conversations", response_model=list[GrokConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[GrokConversationOut]:
    if not grok_store.should_persist(user):
        return []
    rows = grok_store.list_conversations(db, user)
    return [_conversation_out(row) for row in rows]


@router.post("/chat/conversations", response_model=GrokConversationOut, status_code=201)
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


@router.get("/chat/conversations/{conversation_id}", response_model=GrokConversationDetailOut)
def get_conversation(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> GrokConversationDetailOut:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    row = grok_store.get_conversation(db, user, conversation_id)
    return _conversation_detail(row, crypto_enabled=message_crypto.is_enabled(user))


class MessageCryptoEnableIn(BaseModel):
    salt: str | None = Field(default=None, max_length=64)


class EncryptedMessageIn(BaseModel):
    role: str = Field(max_length=16)
    iv: str = Field(min_length=8, max_length=32)
    ct: str = Field(min_length=8, max_length=500_000)
    id: UUID | None = None
    title: str | None = Field(default=None, max_length=80)
    media_ids: list[UUID] = Field(default_factory=list, max_length=5)


class CryptoMigrateIn(BaseModel):
    messages: list[dict] = Field(min_length=1, max_length=200)


@router.get("/chat/crypto")
def get_message_crypto(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    return message_crypto.status(db, user)


@router.post("/chat/crypto/enable")
def enable_message_crypto(
    payload: MessageCryptoEnableIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    body = payload or MessageCryptoEnableIn()
    result = message_crypto.enable(db, user, salt_b64_value=body.salt)
    db.commit()
    return result


@router.post("/chat/crypto/migrate")
def migrate_message_crypto(
    payload: CryptoMigrateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    if not message_crypto.is_enabled(user):
        raise HTTPException(status_code=400, detail="Message encryption is not enabled.")
    migrated = 0
    for item in payload.messages:
        message_id = item.get("id")
        iv = item.get("iv")
        ct = item.get("ct")
        if not message_id or not iv or not ct:
            raise HTTPException(status_code=400, detail="Each item needs id, iv, and ct.")
        try:
            mid = UUID(str(message_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid message id.") from exc
        grok_store.migrate_message_to_encrypted(db, user.id, mid, iv=str(iv), ct=str(ct))
        migrated += 1
    db.commit()
    return {"migrated": migrated, **message_crypto.status(db, user)}


@router.post("/chat/conversations/{conversation_id}/messages", response_model=GrokMessageOut, status_code=201)
def post_encrypted_message(
    conversation_id: UUID,
    payload: EncryptedMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> GrokMessageOut:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    if not message_crypto.is_enabled(user):
        raise HTTPException(status_code=400, detail="Message encryption is not enabled.")
    if payload.role not in {"user", "assistant"}:
        raise HTTPException(status_code=400, detail="role must be user or assistant.")
    conversation = grok_store.owned_conversation(db, user, conversation_id)
    row = grok_store.append_encrypted_message(
        db,
        conversation,
        role=payload.role,
        iv=payload.iv,
        ct=payload.ct,
        message_id=payload.id,
        title=payload.title if payload.role == "user" else None,
    )
    if payload.media_ids:
        chat_attachments.attach_to_message(db, user, row, payload.media_ids)
    db.commit()
    db.refresh(row)
    return _message_out(row, crypto_enabled=True)


@router.patch("/chat/conversations/{conversation_id}", response_model=GrokConversationOut)
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


@router.delete("/chat/conversations/{conversation_id}")
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


class SnippetIn(BaseModel):
    code: str = Field(min_length=1, max_length=4000)


@router.post("/chat/messages/{message_id}/docx")
def download_message_docx(
    message_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    clean: bool = Query(default=False),
) -> Response:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    row = grok_store.owned_assistant_message(db, user, message_id)
    if row.encrypted or row.content is None:
        raise HTTPException(status_code=400, detail="Encrypted messages must be exported in the browser.")
    content = row.content
    if clean:
        from app.services.school_tools import strip_marks

        content = strip_marks(content)
    if not chat_docx.has_word_body(content):
        raise HTTPException(status_code=400, detail=chat_docx.EMPTY_WORD_BODY)
    try:
        payload = chat_docx.build_message_docx(content)
    except ValueError as exc:
        detail = str(exc).strip() or chat_docx.BUILD_WORD_FAIL
        if detail == chat_docx.EMPTY_WORD_BODY:
            raise HTTPException(status_code=400, detail=chat_docx.EMPTY_WORD_BODY) from exc
        raise HTTPException(status_code=400, detail=chat_docx.BUILD_WORD_FAIL) from exc
    filename = chat_docx.docx_filename(content).replace('"', "")
    return Response(
        content=payload,
        media_type=chat_docx.DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/chat/messages/{message_id}/run-snippet")
def run_message_snippet(
    message_id: UUID,
    payload: SnippetIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    from app.services import junior_jobs as jobs

    result = jobs.run_snippet(db, user, message_id, payload.code)
    return {
        "conversation_id": str(result["conversation_id"]),
        "user_message": GrokMessageOut.model_validate(result["user_message"]).model_dump(mode="json"),
        "assistant_message": GrokMessageOut.model_validate(result["assistant_message"]).model_dump(mode="json"),
    }


@router.post("/chat/imagine")
def imagine_image(
    payload: ImagineIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    if message_crypto.is_enabled(user):
        raise HTTPException(status_code=400, detail="Imagine is unavailable while message encryption is on.")
    imagine_service.require_imagine_key()
    prompt = imagine_service.normalize_prompt(payload.prompt)
    if not prompt:
        raise HTTPException(status_code=400, detail="Type a prompt for the image.")
    if payload.conversation_id:
        grok_store.owned_conversation(db, user, payload.conversation_id)
    imagine_service.enforce_imagine_rate_limit(user.id)
    source_ids = list(payload.media_ids or [])
    source_images = []
    if source_ids:
        preview = chat_attachments.preview_files(db, user, source_ids)
        source_images = [item for item in preview if item.get("kind") == "image"]
        if not source_images:
            raise HTTPException(status_code=400, detail=chat_image.MISSING_PHOTO_DETAIL)
    conversation, user_row = imagine_service.persist_imagine_user(
        db,
        user,
        prompt=prompt,
        conversation_id=payload.conversation_id,
        source_media_ids=[source_images[0]["media_id"]] if source_images else None,
    )
    try:
        if source_images:
            source_url = chat_image.owned_image_data_url(db, user, source_images[0])
            result = chat_image.produce_chat_image("edit", prompt, source_url)
            image_bytes = result.payload
            media = imagine_service.save_generated_image(db, user, result.prompt, image_bytes)
            markdown = chat_image.markdown_for_result(result, media.id)
        else:
            image_bytes = imagine_service.generate_image_bytes(prompt)
            media = imagine_service.save_generated_image(db, user, prompt, image_bytes)
            markdown = imagine_service.assistant_image_markdown(prompt, media.id)
    except HTTPException:
        raise
    assistant_row = imagine_service.persist_generated_assistant(
        db,
        user,
        conversation_id=conversation.id,
        markdown=markdown,
        media=media,
        last_model=chat_image.IMAGE_JOB_MODEL,
        last_reasoning=chat_image.IMAGE_JOB_REASONING,
    )
    conversation = grok_store.owned_conversation(db, user, conversation.id)
    return {
        "conversation_id": conversation.id,
        "user_message": _message_out(user_row),
        "assistant_message": _message_out(assistant_row),
    }


# Heavy turns (attachments, working notes) can spend several seconds in setup.
CHAT_SETUP_BUDGET_SEC = 20.0
CHAT_SETUP_TIMEOUT_DETAIL = "Chat stalled before xAI. Try again."


class _SetupStage:
    """Names the last setup step so a stall says where it stalled."""

    def __init__(self) -> None:
        self.name = "start"
        self._started = time.monotonic()

    def mark(self, name: str) -> None:
        self.name = name

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._started) * 1000)


async def _setup_timeout_events(stage_name: str):
    yield chat_service.SSE_PADDING
    await asyncio.sleep(0)
    yield chat_service.encode_sse(
        chat_service.stream_error_event(504, f"{CHAT_SETUP_TIMEOUT_DETAIL} (stalled at {stage_name})")
    )


def _sse_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "Content-Encoding": "identity",
    }


def _image_tool_events(
    request: Request,
    *,
    user_id: UUID,
    persist: bool,
    conversation_id: UUID | None,
    user_message_id: UUID | None,
    user_text: str,
    intent: chat_image.ImageJobIntent,
    thread_images: list[dict],
):
    async def events():
        yield chat_service.SSE_PADDING
        await asyncio.sleep(0)
        meta = {
            "conversation_id": str(conversation_id) if conversation_id else None,
            "user_message_id": str(user_message_id) if user_message_id else None,
            "model": chat_image.IMAGE_JOB_MODEL,
            "model_choice": chat_service.MODEL_AUTO,
            "reasoning_effort": chat_image.IMAGE_JOB_REASONING,
            "stream_status": "generating",
            "delta": chat_image.GENERATING_DELTA,
        }
        yield chat_service.encode_sse({key: value for key, value in meta.items() if value is not None})
        await asyncio.sleep(0)

        job = asyncio.create_task(
            asyncio.to_thread(
                chat_image.run_intercepted_chat_image,
                user_id=user_id,
                persist=persist,
                conversation_id=conversation_id,
                user_text=user_text,
                intent=intent,
                thread_images=thread_images,
            )
        )

        async def _finish_job() -> None:
            try:
                await asyncio.shield(job)
            except Exception:
                log_chat_exception("chat image job failed after disconnect", user=user_id, conversation=conversation_id)

        try:
            while not job.done():
                if await request.is_disconnected():
                    await _finish_job()
                    return
                try:
                    await asyncio.wait_for(asyncio.shield(job), timeout=8.0)
                except asyncio.TimeoutError:
                    yield chat_service.SSE_PADDING
                    yield chat_service.encode_sse({"heartbeat": True})
                    await asyncio.sleep(0)
            turn = job.result()
            if "/api/v1/media/" not in (turn.markdown or "") or not turn.media_id:
                raise HTTPException(status_code=502, detail="Could not generate that image.")
            yield chat_service.encode_sse({"delta": turn.markdown})
            done_meta = {
                "conversation_id": str(conversation_id) if conversation_id else None,
                "assistant_message_id": str(turn.assistant_message_id) if turn.assistant_message_id else None,
                "media_id": str(turn.media_id) if turn.media_id else None,
                "model": chat_image.IMAGE_JOB_MODEL,
                "model_choice": chat_service.MODEL_AUTO,
                "reasoning_effort": chat_image.IMAGE_JOB_REASONING,
            }
            yield chat_service.encode_sse({key: value for key, value in done_meta.items() if value is not None})
            yield chat_service.encode_sse("[DONE]")
        except HTTPException as exc:
            status_code, detail = chat_service.http_exception_detail(exc)
            logger.info(
                "chat image intercept http-%s user=%s conversation=%s",
                status_code,
                user_id,
                conversation_id,
            )
            yield chat_service.encode_sse(chat_service.stream_error_event(status_code, detail))
        except asyncio.CancelledError:
            await _finish_job()
            raise
        except Exception as exc:
            from app.http_limits import redact_secrets

            log_chat_exception("chat image intercept error", user=user_id, conversation=conversation_id)
            yield chat_service.encode_sse(
                chat_service.stream_error_event(500, redact_secrets(str(exc) or exc.__class__.__name__))
            )

    return events()


@router.post("/chat")
async def chat(
    payload: ChatIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> StreamingResponse:
    stage = _SetupStage()
    try:
        # Setup is synchronous DB work. On the event loop a single slow query
        # freezes the whole worker, so every later request 502s.
        return await asyncio.wait_for(
            run_in_threadpool(_chat, payload, request, db, user, stage),
            timeout=CHAT_SETUP_BUDGET_SEC,
        )
    except asyncio.TimeoutError:
        logger.error(
            "chat setup timed out stage=%s ms=%s user=%s",
            stage.name,
            stage.elapsed_ms(),
            getattr(user, "id", None),
        )
        return StreamingResponse(
            _setup_timeout_events(stage.name),
            media_type="text/event-stream",
            headers=_sse_headers(),
        )
    except HTTPException:
        raise
    except MemoryError:
        log_chat_exception("chat memory error", user=getattr(user, "id", None))
        raise HTTPException(status_code=413, detail=chat_service.SEND_THREAD_TOO_LARGE) from None
    except Exception as exc:
        log_chat_exception("chat failed", user=getattr(user, "id", None))
        raise HTTPException(
            status_code=500,
            detail=f"Chat failed ({exc.__class__.__name__}).",
        ) from None


def _chat(
    payload: ChatIn,
    request: Request,
    db: Session,
    user: User,
    stage: _SetupStage | None = None,
) -> StreamingResponse:
    step = (stage or _SetupStage()).mark
    step("auth")
    chat_service.require_key()
    user_id = user.id
    chat_service.enforce_rate_limit(user_id)

    persist = grok_store.should_persist(user)
    conversation_id = payload.conversation_id
    user_message_id: UUID | None = None
    incoming_model = chat_service.normalize_model_choice(payload.model) if payload.model else None
    incoming_reasoning = (
        chat_service.normalize_reasoning_effort(payload.reasoning_effort)
        if payload.reasoning_effort is not None
        else None
    )
    model_choice = incoming_model or chat_service.MODEL_AUTO
    reasoning_choice = incoming_reasoning or chat_service.REASONING_AUTO
    recap_question = bool(payload.recap_question)

    user_text = payload.message.strip()
    media_ids = list(payload.media_ids or [])
    current_files: list[dict] = []
    crypto_on = message_crypto.is_enabled(user)

    def _history_from_override() -> list[dict]:
        if not payload.history_override:
            raise HTTPException(
                status_code=400,
                detail="history_override is required when message encryption is enabled.",
            )
        built = [{"role": turn.role, "content": turn.content, "files": []} for turn in payload.history_override]
        if current_files and built:
            built[-1]["files"] = current_files
        return built

    step("history")
    if persist:
        if crypto_on:
            if payload.retry:
                if not conversation_id:
                    raise HTTPException(status_code=400, detail="Open the thread you want to retry.")
                conversation = grok_store.owned_conversation(db, user, conversation_id)
                pending = grok_store.pending_user_turn(db, conversation_id)
                if not pending:
                    raise HTTPException(status_code=400, detail="Nothing to retry on this thread.")
                grok_store.trim_trailing_assistants(db, conversation_id)
                if not user_text:
                    raise HTTPException(status_code=400, detail="Include the user line when retrying encrypted threads.")
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
            elif conversation_id:
                conversation = grok_store.owned_conversation(db, user, conversation_id)
            else:
                if incoming_model is not None:
                    model_choice = incoming_model
                if incoming_reasoning is not None:
                    reasoning_choice = incoming_reasoning
                stored_reasoning = (
                    chat_service.REASONING_AUTO
                    if model_choice == chat_service.MODEL_AUTO
                    else reasoning_choice
                )
                conversation = grok_store.create_conversation(
                    db, user, model=model_choice, reasoning=stored_reasoning
                )
                conversation_id = conversation.id
            model_choice = chat_service.normalize_model_choice(conversation.model or chat_service.MODEL_AUTO)
            reasoning_choice = chat_service.normalize_reasoning_effort(
                getattr(conversation, "reasoning", None) or chat_service.REASONING_AUTO
            )
            if incoming_model is not None:
                model_choice = incoming_model
                conversation.model = model_choice
            if incoming_reasoning is not None:
                reasoning_choice = incoming_reasoning
            conversation.reasoning = (
                chat_service.REASONING_AUTO
                if model_choice == chat_service.MODEL_AUTO
                else reasoning_choice
            )
            conversation.recap_question = recap_question
            if payload.client_title and payload.client_title.strip():
                conversation.title = payload.client_title.strip()[:80]
            db.add(conversation)
            if media_ids:
                current_files = chat_attachments.preview_files(db, user, media_ids)
            db.commit()
            history = _history_from_override()
        elif payload.retry:
            if not conversation_id:
                raise HTTPException(status_code=400, detail="Open the thread you want to retry.")
            conversation = grok_store.owned_conversation(db, user, conversation_id)
            pending = grok_store.pending_user_turn(db, conversation_id)
            if not pending:
                raise HTTPException(status_code=400, detail="Nothing to retry on this thread.")
            grok_store.trim_trailing_assistants(db, conversation_id)
            if pending.encrypted or pending.content is None:
                raise HTTPException(status_code=400, detail="Retry with the message in the request when encryption is on.")
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
            reasoning_choice = chat_service.normalize_reasoning_effort(
                getattr(conversation, "reasoning", None) or chat_service.REASONING_AUTO
            )
            if incoming_model is not None:
                model_choice = incoming_model
                conversation.model = model_choice
            if incoming_reasoning is not None:
                reasoning_choice = incoming_reasoning
            conversation.reasoning = (
                chat_service.REASONING_AUTO
                if model_choice == chat_service.MODEL_AUTO
                else reasoning_choice
            )
            conversation.recap_question = recap_question
            db.add(conversation)
            db.commit()
            history = grok_store.conversation_history(db, conversation_id)
        elif conversation_id:
            conversation = grok_store.owned_conversation(db, user, conversation_id)
            model_choice = chat_service.normalize_model_choice(conversation.model or chat_service.MODEL_AUTO)
            reasoning_choice = chat_service.normalize_reasoning_effort(
                getattr(conversation, "reasoning", None) or chat_service.REASONING_AUTO
            )
            if incoming_model is not None:
                model_choice = incoming_model
                conversation.model = model_choice
            if incoming_reasoning is not None:
                reasoning_choice = incoming_reasoning
            conversation.reasoning = (
                chat_service.REASONING_AUTO
                if model_choice == chat_service.MODEL_AUTO
                else reasoning_choice
            )
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
            if incoming_model is not None:
                model_choice = incoming_model
            if incoming_reasoning is not None:
                reasoning_choice = incoming_reasoning
            stored_reasoning = (
                chat_service.REASONING_AUTO
                if model_choice == chat_service.MODEL_AUTO
                else reasoning_choice
            )
            conversation = grok_store.create_conversation(
                db, user, model=model_choice, reasoning=stored_reasoning
            )
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
        if incoming_model is not None:
            model_choice = incoming_model
        if incoming_reasoning is not None:
            reasoning_choice = incoming_reasoning
        current_files = chat_attachments.preview_files(db, user, media_ids) if media_ids else []
        history = [{"role": "user", "content": user_text, "files": current_files}]

    if history:
        current_files = history[-1].get("files") or current_files
    this_turn_images = chat_image.this_turn_images(current_files)
    image_intent = chat_image.image_tool_intent(user_text, bool(this_turn_images))
    if image_intent == "edit" and not this_turn_images:
        image_intent = None
    if image_intent in ("edit", "generate"):
        return StreamingResponse(
            _image_tool_events(
                request,
                user_id=user_id,
                persist=persist,
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                user_text=user_text,
                intent=image_intent,
                thread_images=this_turn_images,
            ),
            media_type="text/event-stream",
            headers=_sse_headers(),
        )
    history_for_route = chat_service.drop_trailing_assistants(
        [{"role": item.get("role"), "content": item.get("content") or ""} for item in history]
    )
    step("route")
    history_window = chat_service.thread_window(history_for_route)
    # Route Auto on this turn's typed line only. Extracts/articles must not lift hello to xhigh.
    route_message = (user_text or "").strip() or "attached file"
    resolved_model = chat_service.resolve_model_for_request(
        model_choice,
        route_message,
        history_window,
    )
    resolved_reasoning = chat_service.resolve_reasoning_for_request(
        model_choice,
        reasoning_choice,
        route_message,
        None,
    )
    resolved_reasoning = chat_service.clamp_reasoning_effort(resolved_model, resolved_reasoning)
    from app.services import morning_brief

    mail_specific_text = None
    if mail_tool.mail_action(user_text) and not is_locked(user):
        if mail_service.has_token(db, user):
            try:
                mail_specific_text = mail_tool.specific_mail_reply(mail_service.require_token(db, user), user_text)
            except Exception:
                log_chat_exception("specific mail failed", user=user_id, conversation=conversation_id)
                mail_specific_text = mail_tool.format_specific(
                    "read", [], "", connected=True, error="failed"
                )
        else:
            mail_specific_text = mail_tool.format_specific("read", [], "", connected=False)
    mark_read_text = None
    if mail_specific_text is None and mail_tool.wants_mark_read(user_text) and not is_locked(user):
        if mail_service.has_token(db, user):
            try:
                mark_read_text = mail_tool.mark_read_reply(mail_service.require_token(db, user), user_text)
            except Exception:
                log_chat_exception("mark read failed", user=user_id, conversation=conversation_id)
                mark_read_text = mail_tool.format_mark_read([], marked=0, label="", connected=True, error="failed")
        else:
            mark_read_text = mail_tool.format_mark_read([], marked=0, label="", connected=False)
    news_summary_text = None
    if (
        wants_news_summary(user_text)
        and not is_locked(user)
        and mail_specific_text is None
        and mark_read_text is None
    ):
        try:
            news_summary_text = news_summary_reply(db, user.id, user_text)
        except Exception:
            log_chat_exception("news summary failed", user=user_id, conversation=conversation_id)
            news_summary_text = "News summaries could not be loaded. Try again."
    morning_turn = (
        morning_brief.wants_morning(user_text)
        and not is_locked(user)
        and mark_read_text is None
        and mail_specific_text is None
        and news_summary_text is None
    )
    morning_text = None
    if morning_turn:
        try:
            morning_text = morning_brief.build(db, user)
        except Exception:
            log_chat_exception("morning brief failed", user=user_id, conversation=conversation_id)
            morning_text = "School morning could not be loaded. Try again."
    mail_unread = (
        mail_tool.wants_unread_mail(user_text)
        and not morning_turn
        and mark_read_text is None
        and mail_specific_text is None
        and news_summary_text is None
    )
    if mail_unread:
        resolved_model = chat_service.CURRENT_CHAT_MODEL
        resolved_reasoning = "low"
        resolved_reasoning = chat_service.clamp_reasoning_effort(resolved_model, resolved_reasoning)
    step("prepare")
    excerpt = None
    note_excerpt = None
    article_body = None
    note_body = None
    include_article = bool(payload.include_article)
    include_note = bool(payload.include_note_id)
    working_excerpt = None
    include_meta: dict[str, object] = {}

    def _owned_include_slice(article, *, cap: int | None = None, hard_max: int | None = None):
        try:
            return resolve_include_slice(
                chat_service.article_body_text(article),
                mode=payload.include_mode,
                selection=payload.include_selection,
                heading=payload.include_heading,
                offset=payload.include_offset or 0,
                title=article.title,
                html=getattr(article, "content_html", None),
                cap=cap,
                hard_max=hard_max,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if include_article:
        if not payload.article_id:
            raise HTTPException(status_code=400, detail="Open an article before attaching it to chat.")
        article = _owned_article(db, user, payload.article_id)
        owned_slice = _owned_include_slice(article)
        article_body = owned_slice.text
        excerpt = format_include_excerpt((article.title or "Untitled").strip(), owned_slice)
        excerpt = (
            f"article_id: {article.id}\n"
            f"Open in reader: [{(article.title or 'Untitled').strip()}](#article/{article.id})\n"
            f"{excerpt}"
        )
        include_meta = include_slice_meta(owned_slice)
    if include_note:
        if include_article and payload.article_id == payload.include_note_id:
            note_excerpt = excerpt
            note_body = article_body
        else:
            note = _owned_article(db, user, payload.include_note_id)
            note_slice = _owned_include_slice(note)
            note_body = note_slice.text
            note_excerpt = format_include_excerpt((note.title or "Untitled").strip(), note_slice)
            if not include_meta:
                include_meta = include_slice_meta(note_slice)
    if payload.working_note_id and chat_service.should_attach_working_note(user_text):
        working = _owned_article(db, user, payload.working_note_id)
        if not is_composed_guid(working.guid):
            raise HTTPException(status_code=400, detail="Work in Junior is for StoryKeep-authored notes.")
        work_mode = payload.include_mode
        work_heading = payload.include_heading
        if (not work_mode or work_mode == "auto") and not (work_heading or "").strip():
            guessed = heading_from_instruction(user_text, chat_service.article_body_text(working))
            if guessed:
                work_mode = "heading"
                work_heading = guessed
        try:
            working_slice = resolve_include_slice(
                chat_service.article_body_text(working),
                mode=work_mode,
                selection=payload.include_selection,
                heading=work_heading,
                offset=payload.include_offset or 0,
                title=working.title,
                html=getattr(working, "content_html", None),
                cap=WORKING_NOTE_CHAR_CAP,
                hard_max=WORKING_NOTE_CHAR_CAP,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        working_excerpt = format_include_excerpt((working.title or "Untitled").strip(), working_slice)
        working_excerpt = f"working_note_id: {working.id}\n{working_excerpt}"
        include_meta = include_slice_meta(working_slice)
    include_chars = len(article_body or "")
    if note_body and note_body != article_body:
        include_chars += len(note_body)
    rough_thread = chat_service.messages_for_xai(
        history,
        model=resolved_model,
        db=db,
        user=user,
    )
    working_excerpt = chat_service.cap_working_excerpt(
        working_excerpt,
        thread_chars=chat_service.messages_char_count(rough_thread),
        include_chars=include_chars,
    )
    system_overhead = len(excerpt or "") + len(note_excerpt or "") + len(working_excerpt or "")
    prepared = chat_service.messages_for_xai(
        history,
        model=resolved_model,
        db=db,
        user=user,
        trim_cap=chat_service.thread_trim_cap(system_overhead=system_overhead),
    )
    history_for_xai = chat_service.validate_payload(prepared)
    chat_service.reject_oversized_send(
        history,
        article_body=article_body,
        note_body=note_body,
        working_excerpt=working_excerpt,
        system_overhead=system_overhead,
    )
    has_attachments = any(item.get("files") for item in history)
    step("unread")
    unread_catalog = None if mail_unread else unread_news_block(db, user.id, user_text)
    if unread_catalog:
        history_for_xai = chat_service.validate_payload(
            attach_unread_catalog(history_for_xai, unread_catalog)
        )
    step("calendar")
    calendar_connected = calendars.is_connected(db, user_id) and not is_locked(user)
    step("mail")
    mail_connected = mail_service.has_token(db, user)
    unread_mail_md = None
    if mail_unread:
        if mail_connected:
            try:
                listed = jmap.list_emails(
                    mail_service.require_token(db, user), role="inbox", unseen=True, limit=50
                )
                unread_mail_md = mail_tool.unread_mail_markdown(listed.get("items") or [])
            except Exception:
                unread_mail_md = "Fastmail unread list was unavailable this turn."
        else:
            unread_mail_md = "Fastmail mail is not connected. Open Mail in StoryKeep."
    step("memory")
    memory_block = junior_memory.system_section(db, user)
    chats_enabled = chat_index.can_use(user)
    already_indexed = False
    already_read = False
    read_slice_payload: dict[str, object] | None = None
    index_block: str | None = None
    read_meta: str | None = None
    if chats_enabled:
        if chat_index.wants_index(user_text):
            index_block = chat_index.format_index(chat_index.build_index(db, user))
            already_indexed = True
        elif chat_index.wants_read(user_text):
            chat_id = chat_index.extract_conversation_id(user_text)
            if chat_id:
                try:
                    read_slice_payload = chat_index.read_slice(db, user, chat_id)
                    already_read = True
                    read_meta = (
                        f"Opened Junior chat slice: {read_slice_payload.get('title')} · "
                        f"id={read_slice_payload.get('id')} · "
                        f"truncated={str(bool(read_slice_payload.get('truncated'))).lower()}."
                    )
                except HTTPException:
                    read_meta = "No chat with that id. Use the index. Do not invent a thread."
            else:
                read_meta = chat_index.NEED_ID_SYSTEM
    from app.services import junior_model

    search_enabled = search_tool.owner_can_search(user)
    will_search = search_enabled and search_tool.wants_web_search(user_text)
    will_voices = tts_service.wants_voice_info(user_text)
    owner_ops = user is not None and not is_locked(user)
    railway_enabled = railway_tool.owner_can_use(user)
    github_enabled = github_tool.owner_can_use(user)
    will_railway = railway_tool.wants_railway(user_text)
    will_github = github_tool.wants_github(user_text)
    will_deploy = railway_tool.wants_railway_deploy(user_text)
    cursor_enabled = cursor_agent_tool.owner_can_use(user)
    will_cursor_start = junior_model.should_server_start_agent(
        user_text, configured=cursor_enabled
    )
    ops_turn = owner_ops and junior_model.is_ops_turn(user_text)
    delegate_turn = owner_ops and junior_model.is_delegate_turn(user_text)
    railway_tools_on = owner_ops and (
        ops_turn or chat_service.should_attach_chat_tools(user_text)
    )
    github_tools_on = owner_ops and (
        ops_turn or chat_service.should_attach_chat_tools(user_text)
    )
    cursor_tools_on = owner_ops and (
        delegate_turn or chat_service.should_attach_chat_tools(user_text)
    )
    turn_extras = junior_model.build_turn_extras(
        user_text,
        memory_block=memory_block,
        chats_enabled=chats_enabled,
        index_block=index_block,
        read_meta=read_meta,
        unread_catalog=unread_catalog,
        calendar_connected=calendar_connected,
        calendar_tools=chat_service.should_attach_chat_tools(user_text),
        mail_connected=mail_connected,
        mail_unread=mail_unread,
        unread_mail_md=unread_mail_md,
        search_enabled=search_enabled,
        will_search=will_search,
        railway_enabled=railway_enabled,
        railway_tools=railway_tools_on,
        github_enabled=github_enabled,
        github_tools=github_tools_on,
        cursor_enabled=cursor_enabled,
        cursor_tools=cursor_tools_on,
        ops_turn=ops_turn,
        delegate_turn=delegate_turn,
    )
    pane_note = junior_model.pane_mismatch_note(user_text, payload.pane_name)
    if pane_note:
        turn_extras.append(junior_model.PANE_MISMATCH_APPEND)
    extra_system = junior_model.standing_system(
        db,
        user,
        user_text=user_text,
        extras=turn_extras,
    )
    calendar_tools = (
        [ADD_EVENT_TOOL]
        if calendar_connected and chat_service.should_attach_chat_tools(user_text)
        else None
    )
    mail_tools = (
        [mail_tool.PROPOSE_SEND_TOOL]
        if mail_connected and mail_tool.wants_send_mail(user_text)
        else None
    )
    search_tools = (
        [search_tool.WEB_SEARCH_TOOL]
        if search_enabled
        and will_search
        and not ops_turn
        and not delegate_turn
        and not junior_model.is_cursor_task_turn(user_text)
        else None
    )
    chat_tools = (
        chat_index.TOOLS
        if chats_enabled
        and (
            already_indexed
            or already_read
            or chat_index.wants_index(user_text)
            or chat_index.wants_read(user_text)
            or chat_service.should_attach_chat_tools(user_text)
        )
        else None
    )
    railway_tools = (
        railway_tool.RAILWAY_TOOLS
        if railway_tools_on and (ops_turn or not junior_model.is_cursor_task_turn(user_text))
        else None
    )
    github_tools = (
        github_tool.GITHUB_TOOLS
        if github_tools_on and (ops_turn or not junior_model.is_cursor_task_turn(user_text))
        else None
    )
    cursor_tools = (
        cursor_agent_tool.CURSOR_TOOLS
        if cursor_tools_on and (delegate_turn or not junior_model.is_cursor_task_turn(user_text))
        else None
    )
    tools = (
        *(
            calendar_tools or []),
        *(mail_tools or []),
        *(search_tools or []),
        *(chat_tools or []),
        *(railway_tools or []),
        *(github_tools or []),
        *(cursor_tools or []),
    ) or None
    tool_calls_out: list[dict] = []
    payload_chars = chat_service.messages_char_count(
        chat_service.build_xai_messages(
            history_for_xai,
            excerpt,
            include_article=include_article,
            recap_question=recap_question,
            has_attachments=has_attachments,
            include_note=include_note,
            note_excerpt=note_excerpt,
            working_excerpt=working_excerpt,
            extra_system=extra_system,
        )
    )
    first_byte_timeout = chat_service.first_byte_timeout_sec(
        message_chars=payload_chars,
        has_attachments=has_attachments,
        has_tools=bool(tools),
        will_search=will_search,
        has_working_note=bool(working_excerpt),
        reasoning_effort=resolved_reasoning,
    )
    if will_cursor_start and cursor_enabled:
        # Cursor API create can take ~45s before xAI gets a turn — avoid client first-byte abort.
        first_byte_timeout = max(
            first_byte_timeout,
            cursor_agent_tool.TIMEOUT_SEC + chat_service.CHAT_FIRST_BYTE_TIMEOUT_HEAVY_SEC,
        )

    def _persist_assistant(text: str) -> str | None:
        from app.services import junior_stamp

        cleaned = chat_docx.strip_keep_notes_cta((text or "").strip())
        if crypto_on or not persist or not conversation_id or not cleaned:
            return None
        stamped = junior_stamp.stamp_assistant_content(cleaned)
        try:
            with SessionLocal() as stream_db:
                conversation = grok_store.owned_conversation_for_user(stream_db, user_id, conversation_id)
                assistant_row = grok_store.append_message(
                    stream_db,
                    conversation,
                    role="assistant",
                    content=stamped,
                )
                grok_store.patch_conversation_for_user(
                    stream_db,
                    user_id,
                    conversation_id,
                    last_model=resolved_model,
                    last_reasoning=resolved_reasoning,
                )
                stream_db.commit()
                return str(assistant_row.id)
        except Exception:
            log_chat_exception("Failed to persist assistant reply", user=user_id, conversation=conversation_id)
            return None

    step("stream_open")
    cancelled = asyncio.Event()

    log_slice_id = slice_id_from_meta(include_meta) if include_meta else None
    if read_slice_payload:
        log_slice_id = str(read_slice_payload.get("id") or log_slice_id or "-")

    def _read_chat_messages(extra: str | None) -> list[dict[str, str]] | None:
        if not read_slice_payload:
            return None
        del extra
        return chat_index.model_payload(
            user_text=user_text,
            slice=read_slice_payload,
            standing_memory=extra_system,
        )

    read_payload_first_stream = bool(read_slice_payload)

    def _open_stream(
        extra: str | None,
        stream_tools: list[dict] | None,
        *,
        history: list[dict] | None = None,
        working: str | None = None,
        reasoning: str | None = None,
        fb_timeout: float | None = None,
    ):
        nonlocal read_payload_first_stream
        override = _read_chat_messages(extra) if read_payload_first_stream else None
        read_payload_first_stream = False
        return chat_service.stream_completion(
            history if history is not None else history_for_xai,
            excerpt,
            include_article=include_article,
            recap_question=recap_question,
            model=resolved_model,
            model_choice=model_choice,
            reasoning_effort=reasoning if reasoning is not None else resolved_reasoning,
            user_id=user_id,
            has_attachments=has_attachments,
            include_note=include_note,
            note_excerpt=note_excerpt,
            working_excerpt=working if working is not None else working_excerpt,
            extra_system=extra,
            cancelled=cancelled,
            tools=stream_tools,
            tool_calls_out=tool_calls_out,
            log_chat_id=conversation_id,
            log_slice_id=log_slice_id,
            log_message_id=user_message_id,
            messages_override=override,
            first_byte_timeout=fb_timeout if fb_timeout is not None else first_byte_timeout,
        )

    async def _stream_xai(extra: str | None, stream_tools: list[dict] | None):
        slim_history = chat_service.slim_history_for_retry(history_for_xai)
        slim_reasoning = chat_service.clamp_reasoning_effort(resolved_model, "low")
        slim_timeout = chat_service.first_byte_timeout_sec(
            message_chars=min(payload_chars, chat_service.messages_char_count(slim_history) + 8_000),
            has_attachments=has_attachments,
            has_tools=bool(stream_tools),
            will_search=False,
            has_working_note=False,
            reasoning_effort=slim_reasoning,
        )
        tried_slim = False
        while True:
            try:
                async for piece in chat_service.pace_stream(
                    _open_stream(
                        extra,
                        stream_tools,
                        history=slim_history if tried_slim else None,
                        working="" if tried_slim else None,
                        reasoning=slim_reasoning if tried_slim else None,
                        fb_timeout=slim_timeout if tried_slim else None,
                    )
                ):
                    yield piece
                return
            except HTTPException as exc:
                status_code, detail = chat_service.http_exception_detail(exc)
                if (
                    tried_slim
                    or status_code != 504
                    or detail != chat_service.XAI_SILENT_DETAIL
                ):
                    raise
                tried_slim = True
                tool_calls_out.clear()
                logger.warning(
                    "xAI silent on full context — retrying slim user=%s conversation=%s chars=%s",
                    user_id,
                    conversation_id,
                    payload_chars,
                )

    async def watch_disconnect() -> None:
        try:
            while not cancelled.is_set():
                if await request.is_disconnected():
                    cancelled.set()
                    return
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            return

    async def events():
        assistant_parts: list[str] = []
        started = time.perf_counter()
        ttft_ms: int | None = None
        flushed = False
        saw_text = False
        watch = asyncio.create_task(watch_disconnect())

        async def emit_delta(piece: str) -> None:
            nonlocal ttft_ms, flushed, saw_text
            if not piece:
                return
            assistant_parts.append(piece)
            if ttft_ms is None:
                ttft_ms = int((time.perf_counter() - started) * 1000)
            flushed = True
            saw_text = True

        try:
            yield chat_service.SSE_PADDING
            await asyncio.sleep(0)
            extra = extra_system
            already_searched = False
            already_deployed = False
            deploy_outcome: railway_tool.RailwayOutcome | None = None
            voice_list: list[dict[str, str]] | None = None
            already_started_agent = False
            agent_outcome: cursor_agent_tool.CursorAgentOutcome | None = None
            output_tokens = chat_service.resolved_max_output_tokens()
            open_meta: dict[str, object] = {
                "stream_status": (
                    "searching"
                    if will_search
                    else "starting_agent"
                    if will_cursor_start and cursor_enabled
                    else "deploying"
                    if will_deploy and railway_enabled
                    else "working"
                ),
                "model": resolved_model,
                "model_choice": model_choice,
                "reasoning_effort": resolved_reasoning,
                "pace_note": chat_service.pace_reason(route_message, resolved_reasoning, reasoning_choice),
                "first_byte_timeout_ms": int(first_byte_timeout * 1000),
                "idle_after_ms": int(chat_service.chat_idle_after_token_sec(output_tokens) * 1000),
                "max_output_tokens": output_tokens,
                **include_meta,
            }
            if persist and conversation_id:
                open_meta["conversation_id"] = str(conversation_id)
            if persist and user_message_id:
                open_meta["user_message_id"] = str(user_message_id)
            yield chat_service.encode_sse({key: value for key, value in open_meta.items() if value is not None})
            await asyncio.sleep(0)
            if pane_note:
                await emit_delta(pane_note)
                yield chat_service.encode_sse({"delta": pane_note, "stream_status": "writing"})
                await asyncio.sleep(0)
            if mail_specific_text:
                await emit_delta(mail_specific_text)
                yield chat_service.encode_sse({"delta": mail_specific_text, "stream_status": "writing"})
                if persist and conversation_id:
                    assistant_message_id = _persist_assistant("".join(assistant_parts))
                    if assistant_message_id:
                        yield chat_service.encode_sse(
                            {
                                "conversation_id": str(conversation_id),
                                "assistant_message_id": assistant_message_id,
                                "model": resolved_model,
                                "model_choice": model_choice,
                                "reasoning_effort": resolved_reasoning,
                            }
                        )
                yield chat_service.encode_sse("[DONE]")
                return
            if mark_read_text:
                await emit_delta(mark_read_text)
                yield chat_service.encode_sse({"delta": mark_read_text, "stream_status": "writing"})
                if persist and conversation_id:
                    assistant_message_id = _persist_assistant("".join(assistant_parts))
                    if assistant_message_id:
                        yield chat_service.encode_sse(
                            {
                                "conversation_id": str(conversation_id),
                                "assistant_message_id": assistant_message_id,
                                "model": resolved_model,
                                "model_choice": model_choice,
                                "reasoning_effort": resolved_reasoning,
                            }
                        )
                yield chat_service.encode_sse("[DONE]")
                return
            if news_summary_text:
                await emit_delta(news_summary_text)
                yield chat_service.encode_sse({"delta": news_summary_text, "stream_status": "writing"})
                if persist and conversation_id:
                    assistant_message_id = _persist_assistant("".join(assistant_parts))
                    if assistant_message_id:
                        yield chat_service.encode_sse(
                            {
                                "conversation_id": str(conversation_id),
                                "assistant_message_id": assistant_message_id,
                                "model": resolved_model,
                                "model_choice": model_choice,
                                "reasoning_effort": resolved_reasoning,
                            }
                        )
                yield chat_service.encode_sse("[DONE]")
                return
            if morning_text:
                await emit_delta(morning_text)
                yield chat_service.encode_sse({"delta": morning_text, "stream_status": "writing"})
                if persist and conversation_id:
                    assistant_message_id = _persist_assistant("".join(assistant_parts))
                    if assistant_message_id:
                        yield chat_service.encode_sse(
                            {
                                "conversation_id": str(conversation_id),
                                "assistant_message_id": assistant_message_id,
                                "model": resolved_model,
                                "model_choice": model_choice,
                                "reasoning_effort": resolved_reasoning,
                            }
                        )
                yield chat_service.encode_sse("[DONE]")
                return
            if will_cursor_start:
                agent_source = user_text
                pane_label = (payload.pane_name or "").strip()
                if pane_label:
                    agent_source = (
                        f"{user_text}\n\n"
                        f"Asked from the StoryKeep chat named {pane_label}. "
                        "Stay on the existing Storykeep repository. Do not create a new project."
                    )
                try:
                    start_task = asyncio.create_task(
                        asyncio.to_thread(
                            cursor_agent_tool.start_agent,
                            "",
                            source_message=agent_source,
                            auto_create_pr=True if delegate_turn else None,
                        )
                    )
                    while not start_task.done():
                        if cancelled.is_set() or await request.is_disconnected():
                            cancelled.set()
                            start_task.cancel()
                            return
                        try:
                            await asyncio.wait_for(asyncio.shield(start_task), timeout=8.0)
                        except asyncio.TimeoutError:
                            yield chat_service.SSE_PADDING
                            yield chat_service.encode_sse(
                                {"heartbeat": True, "stream_status": "starting_agent"}
                            )
                            await asyncio.sleep(0)
                    agent_outcome = start_task.result()
                except Exception:
                    log_chat_exception("cursor start failed", user=user_id, conversation=conversation_id)
                    agent_outcome = cursor_agent_tool.CursorAgentOutcome(
                        False,
                        "Cursor Cloud Agent create failed: the start did not finish.",
                        502,
                    )
                already_started_agent = agent_outcome.ok
                if agent_outcome.ok and agent_outcome.agent_id and persist and conversation_id:
                    from app.services.cursor_agent_watch import record_watch

                    record_watch(
                        user_id=user_id,
                        conversation_id=conversation_id,
                        agent_id=agent_outcome.agent_id,
                        agent_url=agent_outcome.agent_url or "",
                        run_id=agent_outcome.run_id,
                        starting_branch=cursor_agent_tool.extract_branch(user_text),
                    )
                note = cursor_agent_tool.summarize_agent_for_user(agent_outcome)
                await emit_delta(note)
                yield chat_service.encode_sse({"delta": note, "stream_status": "writing"})
                if persist and conversation_id:
                    assistant_message_id = _persist_assistant("".join(assistant_parts))
                    if assistant_message_id:
                        yield chat_service.encode_sse(
                            {
                                "conversation_id": str(conversation_id),
                                "assistant_message_id": assistant_message_id,
                                "model": resolved_model,
                                "model_choice": model_choice,
                                "reasoning_effort": resolved_reasoning,
                            }
                        )
                yield chat_service.encode_sse("[DONE]")
                return
            if will_voices:
                voice_list = await asyncio.to_thread(tts_service.list_voices)
                block = tts_service.format_voices_for_model(voice_list)
                extra = f"{extra}\n{block}" if extra else block
            if will_search:
                outcome = await asyncio.to_thread(search_tool.search, user_text)
                already_searched = True
                if outcome.toast:
                    yield chat_service.encode_sse(
                        {
                            "toast": outcome.toast,
                            "toast_kind": "error" if outcome.fatal else "message",
                            "search_status": outcome.status_code,
                        }
                    )
                    await asyncio.sleep(0)
                if outcome.fatal:
                    yield chat_service.encode_sse(
                        chat_service.stream_error_event(outcome.status_code, outcome.detail)
                    )
                    return
                if outcome.empty:
                    extra = f"{extra}\n{search_tool.EMPTY_SYSTEM}" if extra else search_tool.EMPTY_SYSTEM
                else:
                    block = search_tool.format_hits_for_model(outcome.hits)
                    extra = f"{extra}\n{block}" if extra else block
            async def _ops_block(label: str, loader, formatter) -> str:
                try:
                    outcome = await asyncio.to_thread(loader)
                    return formatter(outcome)
                except Exception:
                    log_chat_exception(
                        f"{label} prefetch failed",
                        user=user_id,
                        conversation=conversation_id,
                    )
                    return f"{label} status was unavailable this turn. Answer without it."

            if will_github:
                block = await _ops_block(
                    "GitHub",
                    github_tool.fetch_status,
                    github_tool.format_status_for_model,
                )
                extra = f"{extra}\n{block}" if extra else block
            if will_deploy:
                try:
                    deploy_outcome = await asyncio.to_thread(railway_tool.deploy)
                    already_deployed = deploy_outcome.ok
                    block = railway_tool.format_deploy_for_model(deploy_outcome)
                except Exception:
                    log_chat_exception(
                        "Railway deploy prefetch failed",
                        user=user_id,
                        conversation=conversation_id,
                    )
                    block = "Railway deploy was unavailable this turn. Answer without it."
                extra = f"{extra}\n{block}" if extra else block
            elif will_railway:
                block = await _ops_block(
                    "Railway",
                    railway_tool.fetch_status,
                    railway_tool.format_status_for_model,
                )
                extra = f"{extra}\n{block}" if extra else block
            stream = _stream_xai(extra, tools)
            async for piece in stream:
                if piece is chat_service.STREAM_HEARTBEAT:
                    yield chat_service.SSE_PADDING
                    yield chat_service.encode_sse(
                        {
                            "heartbeat": True,
                            "stream_status": "thinking" if not saw_text else "writing",
                        }
                    )
                    await asyncio.sleep(0)
                    continue
                if cancelled.is_set() or await request.is_disconnected():
                    cancelled.set()
                    if isinstance(piece, str) and piece:
                        assistant_parts.append(piece)
                    _persist_assistant("".join(assistant_parts))
                    return
                if not piece:
                    if not saw_text:
                        yield chat_service.encode_sse({"stream_status": "thinking"})
                        await asyncio.sleep(0)
                    continue
                first = not saw_text
                await emit_delta(piece)
                payload: dict[str, object] = {"delta": piece}
                if first:
                    payload["stream_status"] = "writing"
                yield chat_service.encode_sse(payload)
                await asyncio.sleep(0)
            if cancelled.is_set() or await request.is_disconnected():
                _persist_assistant("".join(assistant_parts))
                return
            follow_blocks: list[str] = []
            followup_query = search_tool.assemble_web_search_query(tool_calls_out)
            if followup_query and not already_searched and search_enabled:
                yield chat_service.encode_sse({"stream_status": "searching"})
                await asyncio.sleep(0)
                outcome = await asyncio.to_thread(search_tool.search, followup_query)
                if outcome.toast:
                    yield chat_service.encode_sse(
                        {
                            "toast": outcome.toast,
                            "toast_kind": "error" if outcome.fatal else "message",
                            "search_status": outcome.status_code,
                        }
                    )
                    await asyncio.sleep(0)
                if outcome.fatal:
                    yield chat_service.encode_sse(
                        chat_service.stream_error_event(outcome.status_code, outcome.detail)
                    )
                    return
                if outcome.empty:
                    follow_blocks.append(search_tool.EMPTY_SYSTEM)
                else:
                    follow_blocks.append(search_tool.format_hits_for_model(outcome.hits))
            chat_call = chat_index.assemble_tool_call(tool_calls_out)
            if chat_call and chats_enabled:
                skip_list = chat_call.get("name") == chat_index.LIST_NAME and already_indexed
                skip_read = chat_call.get("name") == chat_index.READ_NAME and already_read
                if not skip_list and not skip_read:
                    block = await asyncio.to_thread(
                        chat_index.execute_tool_for_user,
                        user_id,
                        conversation_id,
                        chat_call,
                    )
                    if block:
                        follow_blocks.append(block)
            if railway_enabled:
                for railway_call in railway_tool.assemble_tool_calls(tool_calls_out):
                    if railway_call.get("name") == railway_tool.DEPLOY_TOOL_NAME and already_deployed:
                        continue
                    block = await asyncio.to_thread(railway_tool.execute_tool_call, railway_call)
                    if block:
                        follow_blocks.append(block)
            if github_enabled:
                for github_call in github_tool.assemble_tool_calls(tool_calls_out):
                    block = await asyncio.to_thread(github_tool.execute_tool_call, github_call)
                    if block:
                        follow_blocks.append(block)
            if cursor_enabled:
                for cursor_call in cursor_agent_tool.assemble_tool_calls(tool_calls_out):
                    if cursor_call.get("name") == cursor_agent_tool.START_TOOL_NAME and already_started_agent:
                        continue
                    block = await asyncio.to_thread(
                        cursor_agent_tool.execute_tool_call,
                        cursor_call,
                        source_message=user_text,
                    )
                    if block:
                        follow_blocks.append(block)
            if follow_blocks:
                extra = extra_system
                for block in follow_blocks:
                    extra = f"{extra}\n{block}" if extra else block
                async for piece in _stream_xai(extra, None):
                    if piece is chat_service.STREAM_HEARTBEAT:
                        yield chat_service.SSE_PADDING
                        yield chat_service.encode_sse(
                            {
                                "heartbeat": True,
                                "stream_status": "thinking" if not saw_text else "writing",
                            }
                        )
                        await asyncio.sleep(0)
                        continue
                    if cancelled.is_set() or await request.is_disconnected():
                        cancelled.set()
                        if isinstance(piece, str) and piece:
                            assistant_parts.append(piece)
                        _persist_assistant("".join(assistant_parts))
                        return
                    if not piece:
                        if not saw_text:
                            yield chat_service.encode_sse({"stream_status": "thinking"})
                            await asyncio.sleep(0)
                        continue
                    first = not saw_text
                    await emit_delta(piece)
                    payload: dict[str, object] = {"delta": piece}
                    if first:
                        payload["stream_status"] = "writing"
                    yield chat_service.encode_sse(payload)
                    await asyncio.sleep(0)
                if cancelled.is_set() or await request.is_disconnected():
                    _persist_assistant("".join(assistant_parts))
                    return
            if not saw_text and tools and not follow_blocks:
                async for piece in _stream_xai(extra, None):
                    if piece is chat_service.STREAM_HEARTBEAT:
                        yield chat_service.SSE_PADDING
                        yield chat_service.encode_sse(
                            {
                                "heartbeat": True,
                                "stream_status": "thinking" if not saw_text else "writing",
                            }
                        )
                        await asyncio.sleep(0)
                        continue
                    if cancelled.is_set() or await request.is_disconnected():
                        cancelled.set()
                        if isinstance(piece, str) and piece:
                            assistant_parts.append(piece)
                        _persist_assistant("".join(assistant_parts))
                        return
                    if not piece:
                        if not saw_text:
                            yield chat_service.encode_sse({"stream_status": "thinking"})
                            await asyncio.sleep(0)
                        continue
                    first = not saw_text
                    await emit_delta(piece)
                    payload: dict[str, object] = {"delta": piece}
                    if first:
                        payload["stream_status"] = "writing"
                    yield chat_service.encode_sse(payload)
                    await asyncio.sleep(0)
                if cancelled.is_set() or await request.is_disconnected():
                    _persist_assistant("".join(assistant_parts))
                    return
            proposal = assemble_tool_calls(tool_calls_out) or extract_calendar_proposal("".join(assistant_parts))
            mail_proposal = mail_tool.assemble_send_proposal(tool_calls_out) or mail_tool.extract_send_proposal(
                "".join(assistant_parts)
            )
            if proposal and not "".join(assistant_parts).strip():
                note = "I can add this to Fastmail Calendar after you confirm."
                await emit_delta(note)
                yield chat_service.encode_sse({"delta": note, "stream_status": "writing"})
            if mail_proposal and not "".join(assistant_parts).strip():
                note = "I can send this Fastmail message after you confirm."
                await emit_delta(note)
                yield chat_service.encode_sse({"delta": note, "stream_status": "writing"})
            if not saw_text and will_deploy and deploy_outcome is not None:
                note = railway_tool.summarize_deploy_for_user(deploy_outcome)
                await emit_delta(note)
                yield chat_service.encode_sse({"delta": note, "stream_status": "writing"})
            if not saw_text and will_cursor_start and agent_outcome is not None:
                note = cursor_agent_tool.summarize_agent_for_user(agent_outcome)
                await emit_delta(note)
                yield chat_service.encode_sse({"delta": note, "stream_status": "writing"})
            if not saw_text and voice_list is not None:
                note = tts_service.summarize_voices_for_user(voice_list)
                await emit_delta(note)
                yield chat_service.encode_sse({"delta": note, "stream_status": "writing"})
            if not saw_text:
                tool_calls_out.clear()
                async for piece in _stream_xai(None, None):
                    if piece is chat_service.STREAM_HEARTBEAT:
                        yield chat_service.SSE_PADDING
                        yield chat_service.encode_sse(
                            {
                                "heartbeat": True,
                                "stream_status": "thinking" if not saw_text else "writing",
                            }
                        )
                        await asyncio.sleep(0)
                        continue
                    if cancelled.is_set() or await request.is_disconnected():
                        cancelled.set()
                        if isinstance(piece, str) and piece:
                            assistant_parts.append(piece)
                        _persist_assistant("".join(assistant_parts))
                        return
                    if not piece:
                        if not saw_text:
                            yield chat_service.encode_sse({"stream_status": "thinking"})
                            await asyncio.sleep(0)
                        continue
                    first = not saw_text
                    await emit_delta(piece)
                    payload: dict[str, object] = {"delta": piece}
                    if first:
                        payload["stream_status"] = "writing"
                    yield chat_service.encode_sse(payload)
                    await asyncio.sleep(0)
                if cancelled.is_set() or await request.is_disconnected():
                    _persist_assistant("".join(assistant_parts))
                    return
            if not saw_text:
                note = chat_service.EMPTY_REPLY_FALLBACK
                await emit_delta(note)
                yield chat_service.encode_sse({"delta": note, "stream_status": "writing"})
            if persist and conversation_id:
                assistant_text = "".join(assistant_parts).strip()
                assistant_message_id = _persist_assistant(assistant_text)
                if assistant_message_id:
                    yield chat_service.encode_sse(
                        {
                            "conversation_id": str(conversation_id),
                            "assistant_message_id": assistant_message_id,
                            "model": resolved_model,
                            "model_choice": model_choice,
                            "reasoning_effort": resolved_reasoning,
                        }
                    )
            if proposal:
                yield chat_service.encode_sse({"calendar_proposal": proposal})
            if mail_proposal:
                yield chat_service.encode_sse({"mail_proposal": mail_proposal})
            yield chat_service.encode_sse("[DONE]")
        except HTTPException as exc:
            status_code, detail = chat_service.http_exception_detail(exc)
            partial_text = "".join(assistant_parts)
            if not partial_text.strip() and chat_service.is_recoverable_empty_reply(
                status_code, detail
            ):
                note = chat_service.EMPTY_REPLY_FALLBACK
                assistant_parts.append(note)
                await emit_delta(note)
                yield chat_service.encode_sse({"delta": note, "stream_status": "writing"})
                if persist and conversation_id:
                    saved_id = _persist_assistant(note)
                    if saved_id:
                        yield chat_service.encode_sse(
                            {
                                "conversation_id": str(conversation_id),
                                "assistant_message_id": saved_id,
                                "model": resolved_model,
                                "model_choice": model_choice,
                                "reasoning_effort": resolved_reasoning,
                            }
                        )
                yield chat_service.encode_sse("[DONE]")
                return
            flushed = flushed or bool(partial_text)
            saved_id = _persist_assistant(partial_text) if persist else None
            if saved_id and conversation_id:
                yield chat_service.encode_sse(
                    {
                        "conversation_id": str(conversation_id),
                        "assistant_message_id": saved_id,
                        "model": resolved_model,
                        "model_choice": model_choice,
                        "reasoning_effort": resolved_reasoning,
                        "partial": True,
                    }
                )
            yield chat_service.encode_sse(
                chat_service.stream_error_event(status_code, detail, partial=bool(partial_text))
            )
        except asyncio.CancelledError:
            partial_text = "".join(assistant_parts)
            _persist_assistant(partial_text)
            raise
        except Exception as exc:
            partial_text = "".join(assistant_parts)
            from app.http_limits import log_chat_exception, redact_secrets

            log_chat_exception(
                "Chat stream unexpected error",
                user=user_id,
                conversation=conversation_id,
                partial_chars=len(partial_text),
            )
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
                chat_service.stream_error_event(
                    500,
                    redact_secrets(str(exc) or exc.__class__.__name__),
                    partial=bool(partial_text),
                )
            )
        finally:
            cancelled.set()
            watch.cancel()
            try:
                await asyncio.wait_for(watch, timeout=0.2)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers=_sse_headers(),
    )
