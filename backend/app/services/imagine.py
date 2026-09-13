from __future__ import annotations

import base64
import logging
import re
import threading
import time
from collections import defaultdict, deque
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException, status

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


def generate_image_bytes(prompt: str) -> bytes:
    key = require_imagine_key()
    model = (settings.xai_imagine_model or "grok-imagine-image-2.0").strip()
    url = (settings.xai_image_url or "https://api.x.ai/v1/images/generations").strip()
    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "response_format": "b64_json",
    }
    timeout = httpx.Timeout(
        IMAGINE_TIMEOUT_SEC,
        connect=IMAGINE_CONNECT_TIMEOUT_SEC,
        read=IMAGINE_TIMEOUT_SEC,
        write=30.0,
        pool=10.0,
    )
    try:
        with httpx.Client(timeout=timeout) as client:
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
) -> tuple[Any, GrokMessage, GrokMessage]:
    if conversation_id:
        conversation = grok_store.owned_conversation(db, user, conversation_id)
        is_first = not conversation.messages
    else:
        conversation = grok_store.create_conversation(db, user)
        is_first = True
    user_row = grok_store.append_message(
        db,
        conversation,
        role="user",
        content=prompt,
        set_title_from_user=is_first,
    )
    assistant_row = grok_store.append_message(
        db,
        conversation,
        role="assistant",
        content=assistant_image_markdown(prompt, media.id),
    )
    chat_attachments.attach_to_message(
        db,
        user,
        assistant_row,
        [media.id],
        allow_assistant=True,
    )
    db.commit()
    detail = grok_store.get_conversation(db, user, conversation.id)
    messages = list(detail.messages or [])
    if len(messages) < 2:
        raise HTTPException(status_code=500, detail="Could not save that image in the thread.")
    return detail, messages[-2], messages[-1]
