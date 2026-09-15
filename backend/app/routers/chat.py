from __future__ import annotations

import asyncio
import logging
import time
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.deps import get_current_user
from app.models import User
from app.routers.articles import _owned_article
from app.schemas import GrokConversationDetailOut, GrokConversationOut, GrokConversationPatchIn, GrokMessageFileOut, GrokMessageOut
from app.http_limits import log_chat_exception
from app.services import chat as chat_service
from app.services import chat_attachments
from app.services import chat_image
from app.services import chat_docx
from app.services import grok_conversations as grok_store
from app.services import imagine as imagine_service
from app.services.demo_lock import is_locked, reject_locked
from app.services.include_chunk import WORKING_NOTE_CHAR_CAP
from app.services.include_chunk import format_excerpt as format_include_excerpt
from app.services.include_chunk import resolve_include_slice
from app.services.include_chunk import slice_meta as include_slice_meta
from app.services.working_note import heading_from_instruction
from app.services.junior_jobs import UNREAD_READER_SYSTEM, attach_unread_catalog, unread_news_block

router = APIRouter(tags=["chat"])


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

    @model_validator(mode="after")
    def require_text_or_files(self) -> "ChatIn":
        if self.retry:
            return self
        if not self.message.strip() and not self.media_ids:
            raise ValueError("Type a message or attach a file.")
        return self


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
        reasoning=getattr(row, "reasoning", None) or chat_service.REASONING_AUTO,
        last_reasoning=getattr(row, "last_reasoning", None),
        recap_question=bool(row.recap_question),
        saved_note_id=getattr(row, "saved_note_id", None),
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
        "reasoning_efforts": list(chat_service.REASONING_EFFORTS),
        "requests_per_hour": int(settings.chat_requests_per_hour or 120),
        "imagine_requests_per_hour": int(settings.imagine_requests_per_hour or 10),
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
        title_provided="title" in fields,
        model_provided="model" in fields,
        reasoning_provided="reasoning" in fields,
        recap_provided="recap_question" in fields,
        saved_note_provided="saved_note_id" in fields,
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


class SnippetIn(BaseModel):
    code: str = Field(min_length=1, max_length=4000)


@router.post("/chat/messages/{message_id}/docx")
def download_message_docx(
    message_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    clean: bool = Query(default=False),
) -> Response:
    reject_locked(user)
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    row = grok_store.owned_assistant_message(db, user, message_id)
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
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
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
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
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
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    try:
        return await _chat(payload, request, db, user)
    except HTTPException:
        raise
    except MemoryError:
        log_chat_exception("chat memory error", user=getattr(user, "id", None))
        raise HTTPException(status_code=413, detail=chat_service.SEND_CONTEXT_TOO_LARGE) from None
    except Exception:
        log_chat_exception("chat failed", user=getattr(user, "id", None))
        raise HTTPException(status_code=500, detail="Chat failed.") from None


async def _chat(
    payload: ChatIn,
    request: Request,
    db: Session,
    user: User,
) -> StreamingResponse:
    reject_locked(user)
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
    prepared = chat_service.messages_for_xai(history, model=resolved_model, db=db, user=user)
    history_for_xai = chat_service.validate_payload(prepared)
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
    chat_service.reject_oversized_send(history, article_body=article_body, note_body=note_body)
    has_attachments = any(item.get("files") for item in history)
    unread_catalog = unread_news_block(db, user.id, user_text)
    if unread_catalog:
        history_for_xai = attach_unread_catalog(history_for_xai, unread_catalog)

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
                    last_reasoning=resolved_reasoning,
                )
                stream_db.commit()
                return str(assistant_row.id)
        except Exception:
            log_chat_exception("Failed to persist assistant reply", user=user_id, conversation=conversation_id)
            return None

    cancelled = asyncio.Event()
    stream = chat_service.stream_completion(
        history_for_xai,
        excerpt,
        include_article=include_article,
        recap_question=recap_question,
        model=resolved_model,
        model_choice=model_choice,
        reasoning_effort=resolved_reasoning,
        user_id=user_id,
        has_attachments=has_attachments,
        include_note=include_note,
        note_excerpt=note_excerpt,
        working_excerpt=working_excerpt,
        extra_system=UNREAD_READER_SYSTEM if unread_catalog else None,
        cancelled=cancelled,
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
            open_meta: dict[str, object] = {
                "stream_status": "working",
                "model": resolved_model,
                "model_choice": model_choice,
                "reasoning_effort": resolved_reasoning,
                **include_meta,
            }
            if persist and conversation_id:
                open_meta["conversation_id"] = str(conversation_id)
            if persist and user_message_id:
                open_meta["user_message_id"] = str(user_message_id)
            yield chat_service.encode_sse({key: value for key, value in open_meta.items() if value is not None})
            await asyncio.sleep(0)
            async for piece in stream:
                if cancelled.is_set() or await request.is_disconnected():
                    cancelled.set()
                    if piece:
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
                            "reasoning_effort": resolved_reasoning,
                        }
                    )
            yield chat_service.encode_sse("[DONE]")
        except HTTPException as exc:
            status_code, detail = chat_service.http_exception_detail(exc)
            partial_text = "".join(assistant_parts)
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
