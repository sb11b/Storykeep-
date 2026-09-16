from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException

from app.http_limits import redact_secrets
from app.services.tts import _xai_error_detail

logger = logging.getLogger(__name__)


def log_tts_failure(
    *,
    context: str,
    status: int,
    body_snippet: str,
    owner_id: str | None = None,
    chunk_index: int | None = None,
) -> None:
    logger.warning(
        "tts %s failed owner=%s chunk=%s status=%s body=%s",
        context,
        owner_id,
        chunk_index,
        status,
        redact_secrets(body_snippet[:400]),
    )


def raise_for_xai_tts(
    response: httpx.Response,
    *,
    context: str,
    owner_id: str | None = None,
    chunk_index: int = 0,
) -> None:
    body_snippet = (response.text or "").strip()
    log_tts_failure(
        context=context,
        status=response.status_code,
        body_snippet=body_snippet,
        owner_id=owner_id,
        chunk_index=chunk_index,
    )
    detail = _xai_error_detail(response)
    upstream = response.status_code
    lowered = detail.lower()

    if upstream in {401, 403}:
        code = upstream
        message = detail or "Check XAI_API_KEY and voice model access."
    elif upstream == 413 or "too long" in lowered or "payload too large" in lowered:
        code = 413
        message = detail or "Reply too long for one speech request; listen uses chunked playback."
    elif upstream == 429 or "rate limit" in lowered:
        code = 429
        message = detail or "Speech rate limit exceeded. Try again shortly."
    elif upstream in {500, 502, 503, 504}:
        code = 504 if upstream == 504 else 500
        message = detail or "xAI speech service timed out or failed."
    elif upstream == 400 and ("api key" in lowered or "unauthorized" in lowered or "authentication" in lowered):
        code = 401
        message = detail or "xAI rejected the API key or model."
    else:
        code = 502
        message = detail or f"xAI speech failed ({upstream})."

    raise HTTPException(status_code=code, detail=message)
