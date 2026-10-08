from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import settings

from ._shared import (
    CHAT_CONNECT_TIMEOUT_SEC,
    CHAT_FIRST_BYTE_TIMEOUT_HEAVY_SEC,
    CHAT_FIRST_BYTE_TIMEOUT_MAX_SEC,
    CHAT_FIRST_BYTE_TIMEOUT_SEC,
    CHAT_HEALTH_TIMEOUT_SEC,
    DEFAULT_REASONING_EFFORT,
    SEND_THREAD_TOO_LARGE,
    XAI_MODELS_CACHE_SEC,
    XAI_SILENT_DETAIL,
    _models_cache,
    _models_lock,
)
from .model_routing import (
    _canopy_enabled,
    available_models,
    default_full_model,
    rewrite_xai_model,
)

logger = logging.getLogger(__name__)


def chat_url() -> str:
    base = (settings.canopy_base_url or "").strip()
    if base:
        return base.rstrip("/") + "/chat/completions"
    url = (settings.xai_chat_url or "https://api.x.ai/v1/chat/completions").strip()
    return url or "https://api.x.ai/v1/chat/completions"


def responses_url() -> str:
    base = (settings.canopy_base_url or "").strip()
    if base:
        return base.rstrip("/") + "/responses"
    url = chat_url().rstrip("/")
    if url.endswith("chat/completions"):
        return url[: -len("chat/completions")] + "responses"
    return "https://api.x.ai/v1/responses"


def _xai_responses_url() -> str:
    """Always return the xAI responses URL, ignoring Canopy."""
    url = (settings.xai_chat_url or "https://api.x.ai/v1/chat/completions").strip()
    url = url or "https://api.x.ai/v1/chat/completions"
    if url.endswith("/chat/completions"):
        return url[: -len("chat/completions")] + "responses"
    return "https://api.x.ai/v1/responses"


def _xai_key() -> str:
    """Always return the xAI key, ignoring Canopy."""
    key = (settings.xai_api_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat is off until XAI_API_KEY is set on the server (Railway variables).",
        )
    if not key.startswith("xai-"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="XAI_API_KEY must start with xai- (check Railway variables).",
        )
    return key


def key_format_ok() -> bool:
    if _canopy_enabled():
        key = (settings.canopy_api_key or "").strip()
        return bool(key)
    key = (settings.xai_api_key or "").strip()
    return bool(key) and key.startswith("xai-")


def key_configured() -> bool:
    if _canopy_enabled():
        return bool((settings.canopy_api_key or "").strip())
    key = (settings.xai_api_key or "").strip()
    if not key:
        return False
    return key.startswith("xai-")


def require_key() -> str:
    if _canopy_enabled():
        key = (settings.canopy_api_key or "").strip()
        if not key:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Chat is off until CANOPY_API_KEY is set on the server (Railway variables).",
            )
        return key
    key = (settings.xai_api_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat is off until XAI_API_KEY is set on the server (Railway variables).",
        )
    if not key.startswith("xai-"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="XAI_API_KEY must start with xai- (check Railway variables).",
        )
    return key


def first_byte_timeout_sec(
    *,
    message_chars: int,
    has_attachments: bool = False,
    has_tools: bool = False,
    will_search: bool = False,
    has_working_note: bool = False,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
) -> float:
    """Heavy turns (files, working notes, tools) need a longer first-token window."""
    timeout = float(CHAT_FIRST_BYTE_TIMEOUT_SEC)
    if has_attachments or has_working_note:
        timeout = max(timeout, 45.0)
    if has_tools or will_search:
        timeout = max(timeout, 45.0)
    if message_chars > 60_000:
        timeout = max(timeout, CHAT_FIRST_BYTE_TIMEOUT_HEAVY_SEC)
    elif message_chars > 30_000:
        timeout = max(timeout, 35.0)
    if (reasoning_effort or "").strip().lower() in {"high", "xhigh"}:
        timeout = max(timeout, CHAT_FIRST_BYTE_TIMEOUT_HEAVY_SEC)
    return min(timeout, CHAT_FIRST_BYTE_TIMEOUT_MAX_SEC)


def _chat_timeout(*, streaming: bool) -> httpx.Timeout:
    if streaming:
        # Read idle is owned by asyncio.wait_for; httpx must not buffer the whole completion.
        return httpx.Timeout(
            None,
            connect=CHAT_CONNECT_TIMEOUT_SEC,
            read=None,
            write=15.0,
            pool=10.0,
        )
    return httpx.Timeout(
        timeout=CHAT_HEALTH_TIMEOUT_SEC,
        connect=CHAT_CONNECT_TIMEOUT_SEC,
        read=CHAT_HEALTH_TIMEOUT_SEC,
        write=10.0,
        pool=10.0,
    )


def _auth_headers(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _xai_ttft_log(
    *,
    ok: bool,
    ttft_ms: int | None,
    model: str,
    reasoning: str,
    xai_status: int | str | None,
) -> None:
    """One line per turn: spend chip text plus timing. Never logs headers or the API key."""
    from .model_routing import posted_spend_label

    fields = (
        "xAI %s ttft_ms=%s flushed=%s xai_status=%s",
        posted_spend_label(model, reasoning),
        ttft_ms if ttft_ms is not None else -1,
        "ok" if ok else "silent",
        xai_status,
    )
    if ok:
        logger.info(*fields)
    else:
        logger.warning(*fields)


def _transport_error_detail(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.ConnectTimeout):
        return f"xAI unreachable: connection timed out after {int(CHAT_CONNECT_TIMEOUT_SEC)}s"
    if isinstance(exc, httpx.ConnectError):
        return f"xAI unreachable: {exc}"
    if isinstance(exc, httpx.ReadTimeout):
        return XAI_SILENT_DETAIL
    return f"xAI unreachable: {exc}"


def map_xai_http_error(status_code: int, detail: str, model: str) -> HTTPException:
    cleaned = (detail or "").strip() or f"xAI returned HTTP {status_code}."
    lowered = cleaned.lower()
    if status_code == 401:
        return HTTPException(status_code=401, detail="xAI auth failed")
    if status_code == 404:
        return HTTPException(status_code=400, detail=f"Invalid xAI model: {model}")
    if status_code == 413 or "context length" in lowered or "payload too large" in lowered:
        return HTTPException(status_code=413, detail=SEND_THREAD_TOO_LARGE)
    if status_code in {400, 422}:
        return HTTPException(status_code=502, detail=cleaned)
    return HTTPException(status_code=502, detail=f"xAI HTTP {status_code}: {cleaned}")


def parse_xai_error_body(raw: str, status_code: int) -> str:
    text = (raw or "").strip()
    if not text:
        return f"xAI returned HTTP {status_code} with no body."
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text[:300]
    if isinstance(parsed, dict):
        err = parsed.get("error")
        if isinstance(err, dict):
            message = err.get("message") or err.get("code")
            if isinstance(message, str) and message.strip():
                return message.strip()[:300]
        for key in ("message", "detail", "error"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:300]
    return text[:300]


def fetch_xai_model_ids(key: str) -> set[str]:
    global _models_cache
    now = time.time()
    with _models_lock:
        if _models_cache and now - _models_cache[0] < XAI_MODELS_CACHE_SEC:
            return _models_cache[1]
    names: set[str] = set(available_models())
    try:
        with httpx.Client(timeout=_chat_timeout(streaming=False)) as client:
            response = client.get(
                "https://api.x.ai/v1/models",
                headers=_auth_headers(key),
            )
            if response.status_code == 200:
                payload = response.json()
                for row in payload.get("data") or []:
                    if isinstance(row, dict):
                        model_id = row.get("id")
                        if isinstance(model_id, str) and model_id.strip():
                            names.add(model_id.strip())
                        for alias in row.get("aliases") or []:
                            if isinstance(alias, str) and alias.strip():
                                names.add(alias.strip())
    except httpx.HTTPError as exc:
        logger.warning("xAI model list fetch failed: %s", exc)
    with _models_lock:
        _models_cache = (now, names)
    return names


def validate_xai_model(model: str) -> None:
    key = require_key()
    try:
        with httpx.Client(timeout=_chat_timeout(streaming=False)) as client:
            response = client.get(
                f"https://api.x.ai/v1/models/{model}",
                headers=_auth_headers(key),
            )
            if response.status_code == 404:
                raise HTTPException(status_code=400, detail=f"Invalid xAI model: {model}")
            if response.status_code == 401:
                raise HTTPException(status_code=401, detail="xAI auth failed")
            if response.status_code >= 400:
                detail = parse_xai_error_body(response.text, response.status_code)
                raise HTTPException(status_code=400, detail=detail)
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=_transport_error_detail(exc)) from exc
