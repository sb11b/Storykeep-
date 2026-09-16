"""Clip STT: POST audio to xAI. Never log raw audio or API keys."""

from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.http_limits import redact_secrets
from app.models import User
from app.services.demo_lock import is_locked
from app.services.stt_limits import enforce_stt_rate_limit

logger = logging.getLogger(__name__)

XAI_STT_URL = "https://api.x.ai/v1/stt"
MAX_CLIP_BYTES = 8 * 1024 * 1024
MIN_CLIP_BYTES = 64
STT_TIMEOUT = httpx.Timeout(45.0, connect=10.0)

ALLOWED_TYPES = frozenset(
    {
        "audio/webm",
        "audio/wav",
        "audio/wave",
        "audio/x-wav",
        "audio/ogg",
        "audio/opus",
        "audio/mpeg",
        "audio/mp4",
        "audio/m4a",
        "audio/x-m4a",
        "audio/aac",
        "application/octet-stream",
    }
)


def key_configured() -> bool:
    return bool((settings.xai_api_key or "").strip())


def _content_type(raw: str | None, filename: str) -> str:
    value = (raw or "").split(";", 1)[0].strip().lower()
    if value in ALLOWED_TYPES and value != "application/octet-stream":
        return value
    name = (filename or "").lower()
    if name.endswith(".wav"):
        return "audio/wav"
    if name.endswith(".webm"):
        return "audio/webm"
    if name.endswith(".ogg"):
        return "audio/ogg"
    if name.endswith(".opus"):
        return "audio/opus"
    if name.endswith(".m4a") or name.endswith(".mp4"):
        return "audio/mp4"
    if name.endswith(".mp3"):
        return "audio/mpeg"
    return value or "audio/webm"


def _filename_for(content_type: str, filename: str) -> str:
    name = (filename or "").strip() or "clip.webm"
    if "." in name and not name.startswith("."):
        return name.split("/")[-1][:80]
    mapping = {
        "audio/wav": "clip.wav",
        "audio/wave": "clip.wav",
        "audio/x-wav": "clip.wav",
        "audio/webm": "clip.webm",
        "audio/ogg": "clip.ogg",
        "audio/opus": "clip.opus",
        "audio/mpeg": "clip.mp3",
        "audio/mp4": "clip.m4a",
        "audio/m4a": "clip.m4a",
        "audio/x-m4a": "clip.m4a",
        "audio/aac": "clip.aac",
    }
    return mapping.get(content_type, "clip.webm")


def transcribe_clip(
    user: User,
    payload: bytes,
    *,
    content_type: str | None,
    filename: str | None,
) -> dict[str, str]:
    if is_locked(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="STT is not enabled on this account",
        )
    if not key_configured():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="STT failed (503)")
    enforce_stt_rate_limit(user.id)
    data = payload or b""
    if len(data) < MIN_CLIP_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty blob")
    if len(data) > MAX_CLIP_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="STT failed (413)")
    ctype = _content_type(content_type, filename or "")
    if ctype not in ALLOWED_TYPES and not ctype.startswith("audio/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="STT failed (400)")
    name = _filename_for(ctype, filename or "")
    key = (settings.xai_api_key or "").strip()
    logger.info("stt clip bytes=%s type=%s", len(data), ctype)
    try:
        with httpx.Client(timeout=STT_TIMEOUT) as client:
            response = client.post(
                XAI_STT_URL,
                headers={"Authorization": f"Bearer {key}"},
                data={"language": "en", "format": "true"},
                files={"file": (name, data, ctype)},
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="STT failed (504)") from exc
    except httpx.HTTPError as exc:
        logger.info("stt clip upstream error=%s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="STT failed (502)") from exc

    if response.status_code >= 400:
        code = int(response.status_code)
        mapped = code if 400 <= code < 500 else 502
        logger.info("stt clip upstream_status=%s", mapped)
        raise HTTPException(status_code=mapped, detail=redact_secrets(f"STT failed ({mapped})"))

    try:
        body = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="STT failed (502)") from exc
    text = ""
    if isinstance(body, dict):
        raw = body.get("text")
        if isinstance(raw, str):
            text = raw.strip()
    if not text:
        raise HTTPException(status_code=502, detail="STT failed (empty transcript)")
    return {"text": text}
