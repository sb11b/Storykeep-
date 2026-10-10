"""Owns the chat route's SSE plumbing (headers, setup-timeout events, image-tool event streams) extracted from chat_stream."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from fastapi import HTTPException, Request

from app.http_limits import log_chat_exception
from app.services import chat as chat_service
from app.services import chat_image

logger = logging.getLogger(__name__)

CHAT_SETUP_TIMEOUT_DETAIL = "Chat stalled before xAI. Try again."


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
