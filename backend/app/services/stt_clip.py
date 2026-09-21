"""Clip STT: POST audio to xAI. Never log raw audio or API keys."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.http_limits import redact_secrets
from app.models import User
from app.services.demo_lock import is_locked
from app.services.stt_limits import enforce_stt_rate_limit

logger = logging.getLogger(__name__)

XAI_STT_URL = "https://api.x.ai/v1/stt"
STT_MODEL_PRIMARY = "grok-voice-transcribe-2.0"
STT_MODEL_FALLBACK = "grok-voice-transcribe-1.0"
MAX_CLIP_BYTES = 500 * 1024 * 1024
MIN_CLIP_BYTES = 256
STT_TIMEOUT = httpx.Timeout(120.0, connect=15.0)

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
        "audio/flac",
    }
)


def key_configured() -> bool:
    return bool((settings.xai_api_key or "").strip())


def _content_type(raw: str | None, filename: str) -> str:
    value = (raw or "").split(";", 1)[0].strip().lower()
    if value == "application/octet-stream":
        value = ""
    if value in ALLOWED_TYPES:
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
    if name.endswith(".aac"):
        return "audio/aac"
    if name.endswith(".flac"):
        return "audio/flac"
    return value or "audio/webm"


def _filename_for(content_type: str, filename: str) -> str:
    name = (filename or "").strip()
    if name and "." in name and not name.startswith("."):
        return name.split("/")[-1][:80]
    mapping = {
        "audio/wav": "audio.wav",
        "audio/wave": "audio.wav",
        "audio/x-wav": "audio.wav",
        "audio/webm": "audio.webm",
        "audio/ogg": "audio.ogg",
        "audio/opus": "audio.opus",
        "audio/mpeg": "audio.mp3",
        "audio/mp4": "audio.mp4",
        "audio/m4a": "audio.mp4",
        "audio/x-m4a": "audio.mp4",
        "audio/aac": "audio.aac",
        "audio/flac": "audio.flac",
    }
    return mapping.get(content_type, "audio.webm")


def _post_clip(
    client: httpx.Client,
    key: str,
    name: str,
    data: bytes,
    content_type: str,
    model: str,
) -> httpx.Response:
    # xAI requires non-file fields before the file field in multipart form data.
    parts: list[tuple[str, tuple[str | None, str | bytes | None] | tuple[str, bytes, str]]] = [
        ("model", (None, model)),
        ("language", (None, "en")),
        ("format", (None, "true")),
        ("file", (name, data, content_type)),
    ]
    return client.post(
        XAI_STT_URL,
        headers={"Authorization": f"Bearer {key}"},
        files=parts,
    )


def _should_fallback_model(response: httpx.Response) -> bool:
    code = int(response.status_code)
    if code == 404:
        return True
    if code not in {400, 422}:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    err = body.get("error") or body.get("detail") or body.get("message") or ""
    text = err if isinstance(err, str) else str(err)
    lowered = text.lower()
    return "model" in lowered or "not found" in lowered


def _upstream_error(response: httpx.Response) -> tuple[int, str]:
    code = int(response.status_code)
    mapped = code if 400 <= code < 500 else 502
    message = f"STT failed ({mapped})"
    try:
        body = response.json()
        err = body.get("error") or body.get("detail") or body.get("message")
        if isinstance(err, dict):
            err = err.get("message") or str(err)
        if isinstance(err, str) and err.strip():
            message = redact_secrets(err.strip()[:240])
    except ValueError:
        text = (response.text or "").strip()
        if text:
            message = redact_secrets(text[:240])
    return mapped, message


def _parse_transcript(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    for key in ("text", "transcript"):
        raw = body.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    nested = body.get("data")
    if isinstance(nested, dict):
        for key in ("text", "transcript"):
            raw = nested.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    results = body.get("results")
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict):
            for key in ("transcript", "text"):
                raw = first.get(key)
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
    return ""


def _empty_payload(data: bytes, ctype: str, response: httpx.Response) -> dict[str, Any]:
    snippet = redact_secrets((response.text or "")[:500])
    logger.info(
        "stt clip empty xai_status=%s mime=%s bytes=%s body=%s",
        response.status_code,
        ctype,
        len(data),
        snippet,
    )
    return {"text": "", "error": "empty transcript", "bytes": len(data), "mime": ctype}


def transcribe_clip(
    user: User,
    payload: bytes,
    *,
    content_type: str | None,
    filename: str | None,
    model: str | None = None,
) -> dict[str, Any]:
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
    primary = (model or STT_MODEL_PRIMARY).strip() or STT_MODEL_PRIMARY
    logger.info("stt clip bytes=%s type=%s name=%s model=%s", len(data), ctype, name, primary)
    try:
        with httpx.Client(timeout=STT_TIMEOUT) as client:
            response = _post_clip(client, key, name, data, ctype, primary)
            if response.status_code >= 400 and _should_fallback_model(response):
                logger.info("stt clip retry model=%s", STT_MODEL_FALLBACK)
                response = _post_clip(client, key, name, data, ctype, STT_MODEL_FALLBACK)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="STT failed (504)") from exc
    except httpx.HTTPError as exc:
        logger.info("stt clip upstream error=%s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="STT failed (502)") from exc

    if response.status_code >= 400:
        mapped, message = _upstream_error(response)
        logger.info("stt clip upstream_status=%s body=%s", mapped, redact_secrets((response.text or "")[:500]))
        raise HTTPException(status_code=mapped, detail=message)

    try:
        body = response.json()
    except ValueError as exc:
        logger.info(
            "stt clip unreadable json mime=%s bytes=%s body=%s",
            ctype,
            len(data),
            redact_secrets((response.text or "")[:500]),
        )
        raise HTTPException(status_code=502, detail="STT failed (502)") from exc

    text = _parse_transcript(body)
    if not text:
        return _empty_payload(data, ctype, response)
    return {"text": text, "bytes": len(data), "mime": ctype}
