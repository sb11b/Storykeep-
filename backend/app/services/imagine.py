from __future__ import annotations

import base64
import logging
import re
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import GrokMessage, NoteMedia, User
from app.services import chat as chat_service
from app.services import chat_attachments
from app.services import grok_conversations as grok_store
from app.services.note_media import save_note_media

logger = logging.getLogger(__name__)

PROMPT_MAX = 4000
IMAGINE_CONNECT_TIMEOUT_SEC = 10.0
IMAGINE_TIMEOUT_SEC = 120.0
_DATA_URI_PREFIX = re.compile(r"^data:image/[^;]+;base64,", re.I)

_rate_lock = threading.Lock()
_imagine_hits: dict[str, deque[float]] = defaultdict(deque)


def normalize_prompt(raw: str | None) -> str:
    return " ".join((raw or "").split())


def image_alt(prompt: str) -> str:
    cleaned = normalize_prompt(prompt).replace("[", "").replace("]", "").replace("(", "").replace(")", "")
    return (cleaned[:80] or "generated image").rstrip()


def assistant_image_markdown(prompt: str, media_id: UUID) -> str:
    return f"Here's the image.\n\n![{image_alt(prompt)}](/api/v1/media/{media_id})"


def assistant_edit_markdown(prompt: str, media_id: UUID) -> str:
    return f"Here's the edited image.\n\n![{image_alt(prompt)}](/api/v1/media/{media_id})"


def assistant_inspired_markdown(prompt: str, media_id: UUID) -> str:
    return (
        "Here's a new generated portrait inspired by your photo — not a pixel-perfect edit.\n\n"
        f"![{image_alt(prompt)}](/api/v1/media/{media_id})"
    )


def require_imagine_key() -> str:
    try:
        return chat_service.require_key()
    except HTTPException as exc:
        if exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Image generation is off until XAI_API_KEY is set on the server (Railway variables).",
            ) from exc
        raise


def enforce_imagine_rate_limit(user_id: UUID, now: float | None = None) -> None:
    limit = max(1, int(settings.imagine_requests_per_hour or 10))
    window = 3600.0
    stamp = now if now is not None else time.time()
    key = str(user_id)
    with _rate_lock:
        hits = _imagine_hits[key]
        while hits and stamp - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Image limit is {limit} per hour. Try again later.",
            )
        hits.append(stamp)


def _xai_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            message = err.get("message") or err.get("type")
            if message:
                return str(message).strip()[:300]
        if isinstance(err, str) and err.strip():
            return err.strip()[:300]
        detail = payload.get("detail") or payload.get("message")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()[:300]
    text = (response.text or "").strip()
    return text[:300] if text else f"xAI returned HTTP {response.status_code}."


def map_imagine_http_error(status_code: int, detail: str, model: str) -> HTTPException:
    cleaned = (detail or "").strip() or f"xAI returned HTTP {status_code}."
    if status_code == 401:
        return HTTPException(status_code=401, detail="xAI auth failed")
    if status_code == 429:
        return HTTPException(
            status_code=429,
            detail="xAI is rate-limiting image generation. Try again later.",
        )
    if status_code == 404:
        return HTTPException(status_code=400, detail=f"Invalid xAI image model: {model}")
    if status_code == 400:
        return HTTPException(status_code=400, detail=cleaned)
    return HTTPException(status_code=502, detail=f"Could not generate that image: {cleaned}")


def decode_b64_image(raw: str) -> bytes:
    text = (raw or "").strip()
    if not text:
        raise HTTPException(status_code=502, detail="xAI did not return an image.")
    text = _DATA_URI_PREFIX.sub("", text)
    try:
        payload = base64.b64decode(text, validate=False)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="xAI returned an image that could not be read.") from exc
    if not payload:
        raise HTTPException(status_code=502, detail="xAI did not return an image.")
    return payload


def extract_image_bytes(body: dict[str, Any], client: httpx.Client | None = None) -> bytes:
    items = body.get("data") if isinstance(body, dict) else None
    if not isinstance(items, list) or not items:
        raise HTTPException(status_code=502, detail="xAI did not return an image.")
    first = items[0] if isinstance(items[0], dict) else {}
    b64 = first.get("b64_json")
    if isinstance(b64, str) and b64.strip():
        return decode_b64_image(b64)
    url = first.get("url")
    if isinstance(url, str) and url.startswith("http"):
        if client is None:
            raise HTTPException(status_code=502, detail="xAI did not return an image.")
        try:
            response = client.get(url, timeout=30.0)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Could not download the generated image.") from exc
        if response.status_code >= 400 or not response.content:
            raise HTTPException(status_code=502, detail="Could not download the generated image.")
        return response.content
    raise HTTPException(status_code=502, detail="xAI did not return an image.")


def _image_timeout() -> httpx.Timeout:
    return httpx.Timeout(
        IMAGINE_TIMEOUT_SEC,
        connect=IMAGINE_CONNECT_TIMEOUT_SEC,
        read=IMAGINE_TIMEOUT_SEC,
        write=30.0,
        pool=10.0,
    )


def _post_xai_image(url: str, payload: dict[str, Any]) -> bytes:
    key = require_imagine_key()
    model = str(payload.get("model") or (settings.xai_imagine_model or "grok-imagine-image-2.0").strip())
    try:
        with httpx.Client(timeout=_image_timeout()) as client:
            response = client.post(url, headers=chat_service._auth_headers(key), json=payload)
            if response.status_code >= 400:
                raise map_imagine_http_error(response.status_code, _xai_error_text(response), model)
            try:
                body = response.json()
            except Exception as exc:
                raise HTTPException(status_code=502, detail="xAI image response was not JSON.") from exc
            if not isinstance(body, dict):
                raise HTTPException(status_code=502, detail="xAI did not return an image.")
            return extract_image_bytes(body, client)
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="Timed out waiting for the image. Try a shorter prompt.",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach xAI for image generation: {exc}") from exc


def generate_image_bytes(prompt: str) -> bytes:
    model = (settings.xai_imagine_model or "grok-imagine-image-2.0").strip()
    url = (settings.xai_image_url or "https://api.x.ai/v1/images/generations").strip()
    payload = {
        "model": model,
        "prompt": prompt[:PROMPT_MAX],
        "n": 1,
        "response_format": "b64_json",
    }
    return _post_xai_image(url, payload)


MAX_EDIT_RAW_BYTES = 1_500_000
MAX_EDIT_SIDE = 2048


def edit_source_data_url(payload: bytes, content_type: str) -> str:
    """Encode an owned upload as a data URI. Never fetch a remote URL."""
    if not payload:
        raise HTTPException(status_code=400, detail="That photo is empty.")
    mime = (content_type or "image/jpeg").split(";")[0].strip() or "image/jpeg"
    if not mime.startswith("image/"):
        mime = "image/jpeg"
    if len(payload) <= MAX_EDIT_RAW_BYTES and mime.startswith("image/"):
        encoded = base64.b64encode(payload).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    try:
        from PIL import Image
        import io

        image = Image.open(io.BytesIO(payload))
        image = image.convert("RGB")
        image.thumbnail((MAX_EDIT_SIDE, MAX_EDIT_SIDE))
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=88, optimize=True)
        data = buf.getvalue()
    except Exception as exc:
        logger.exception("Could not compress chat image for Imagine edit")
        raise HTTPException(status_code=400, detail="Could not read that photo.") from exc
    if not data:
        raise HTTPException(status_code=400, detail="Could not read that photo.")
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def edit_image_bytes(prompt: str, image_data_url: str) -> bytes:
    source = (image_data_url or "").strip()
    if not source.startswith("data:image/"):
        raise HTTPException(
            status_code=400,
            detail="Only photos already uploaded in this thread can be edited.",
        )
    model = (settings.xai_imagine_model or "grok-imagine-image-2.0").strip()
    url = (settings.xai_image_edit_url or "https://api.x.ai/v1/images/edits").strip()
    payload = {
        "model": model,
        "prompt": (prompt or "")[:PROMPT_MAX],
        "image": {"url": source, "type": "image_url"},
    }
    return _post_xai_image(url, payload)


DESCRIBE_TIMEOUT_SEC = 20.0
DESCRIBE_PROMPT = (
    "Describe this portrait in 80 words for an image generator: apparent age, hair, beard or "
    "facial hair, skin, clothing, pose, camera framing, lighting, and background. No commentary."
)


def describe_image_briefly(image_data_url: str) -> str:
    source = (image_data_url or "").strip()
    if not source.startswith("data:image/"):
        raise HTTPException(
            status_code=400,
            detail="Only photos already uploaded in this thread can be described.",
        )
    key = require_imagine_key()
    url = (settings.xai_chat_url or "https://api.x.ai/v1/chat/completions").strip()
    payload = {
        "model": (settings.xai_chat_model or "grok-4.6").strip(),
        "reasoning_effort": "low",
        "max_tokens": 220,
        "temperature": 0.2,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": DESCRIBE_PROMPT},
                    {"type": "image_url", "image_url": {"url": source, "detail": "low"}},
                ],
            }
        ],
    }
    timeout = httpx.Timeout(
        DESCRIBE_TIMEOUT_SEC,
        connect=IMAGINE_CONNECT_TIMEOUT_SEC,
        read=DESCRIBE_TIMEOUT_SEC,
        write=15.0,
        pool=10.0,
    )
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, headers=chat_service._auth_headers(key), json=payload)
            if response.status_code >= 400:
                raise HTTPException(
                    status_code=502,
                    detail="Could not look at that photo to generate a new image.",
                )
            body = response.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not look at that photo to generate a new image.",
        ) from exc
    choices = body.get("choices") if isinstance(body, dict) else None
    if not isinstance(choices, list) or not choices:
        raise HTTPException(status_code=502, detail="Could not look at that photo.")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str) and content.strip():
        return content.strip()[:800]
    if isinstance(content, list):
        parts = [
            str(part.get("text") or "").strip()
            for part in content
            if isinstance(part, dict) and part.get("type") in (None, "text")
        ]
        joined = " ".join(item for item in parts if item).strip()
        if joined:
            return joined[:800]
    raise HTTPException(status_code=502, detail="Could not look at that photo.")


def save_generated_image(db: Any, user: User, prompt: str, payload: bytes) -> NoteMedia:
    filename = f"{image_alt(prompt)[:40] or 'imagine'}.png"
    try:
        return save_note_media(db, user, filename, payload, "image/png")
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc) or "Could not store that image.") from exc


def persist_imagine_turn(
    db: Any,
    user: User,
    *,
    prompt: str,
    conversation_id: UUID | None,
    media: NoteMedia,
    source_media_ids: list[UUID] | None = None,
    assistant_content: str | None = None,
    last_model: str | None = None,
    last_reasoning: str | None = None,
) -> tuple[Any, GrokMessage, GrokMessage]:
    if conversation_id:
        conversation = grok_store.owned_conversation(db, user, conversation_id)
        is_first = not conversation.messages
    else:
        conversation = grok_store.create_conversation(db, user)
        is_first = True
    now = datetime.now(timezone.utc)
    user_row = grok_store.append_message(
        db,
        conversation,
        role="user",
        content=prompt,
        set_title_from_user=is_first,
        created_at=now,
    )
    if source_media_ids:
        chat_attachments.attach_to_message(db, user, user_row, source_media_ids)
    assistant_row = grok_store.append_message(
        db,
        conversation,
        role="assistant",
        content=assistant_content or assistant_image_markdown(prompt, media.id),
        created_at=now + timedelta(milliseconds=1),
    )
    chat_attachments.attach_to_message(
        db,
        user,
        assistant_row,
        [media.id],
        allow_assistant=True,
    )
    grok_store.patch_conversation_for_user(
        db,
        user.id,
        conversation.id,
        last_model=last_model,
        last_reasoning=last_reasoning,
    )
    db.commit()
    user_row = db.scalar(
        select(GrokMessage).options(selectinload(GrokMessage.files)).where(GrokMessage.id == user_row.id)
    )
    assistant_row = db.scalar(
        select(GrokMessage)
        .options(selectinload(GrokMessage.files))
        .where(GrokMessage.id == assistant_row.id)
    )
    if user_row is None or assistant_row is None:
        raise HTTPException(status_code=500, detail="Could not save that image in the thread.")
    conversation = grok_store.owned_conversation(db, user, conversation.id)
    return conversation, user_row, assistant_row


def persist_generated_assistant(
    db: Any,
    user: User,
    *,
    conversation_id: UUID,
    markdown: str,
    media: NoteMedia,
    last_model: str | None = None,
    last_reasoning: str | None = None,
) -> GrokMessage:
    conversation = grok_store.owned_conversation(db, user, conversation_id)
    assistant_row = grok_store.append_message(
        db,
        conversation,
        role="assistant",
        content=markdown,
    )
    chat_attachments.attach_to_message(
        db,
        user,
        assistant_row,
        [media.id],
        allow_assistant=True,
    )
    grok_store.patch_conversation_for_user(
        db,
        user.id,
        conversation_id,
        last_model=last_model,
        last_reasoning=last_reasoning,
    )
    db.commit()
    assistant_row = db.scalar(
        select(GrokMessage)
        .options(selectinload(GrokMessage.files))
        .where(GrokMessage.id == assistant_row.id)
    )
    if assistant_row is None:
        raise HTTPException(status_code=500, detail="Could not save that image in the thread.")
    return assistant_row
