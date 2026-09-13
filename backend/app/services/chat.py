from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from typing import Any, Iterator
from uuid import UUID

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.models import Article

logger = logging.getLogger(__name__)

MODEL_AUTO = "auto"
CHAT_STREAM_TIMEOUT_SEC = 45.0
CHAT_CONNECT_TIMEOUT_SEC = 8.0
CHAT_FIRST_BYTE_TIMEOUT_SEC = 8.0
CHAT_HEALTH_TIMEOUT_SEC = 10.0
XAI_SILENT_DETAIL = "xAI silent"
XAI_MODELS_CACHE_SEC = 900.0
CODE_KEYWORDS = (
    "python",
    "javascript",
    "typescript",
    "java",
    "sql",
    "debug",
    "error",
    "stack trace",
    "function",
    "class ",
    "import ",
    "def ",
    "const ",
    "let ",
    "var ",
    "algorithm",
    "homework",
    "assignment",
    "implement",
    "leetcode",
    "compile",
    "syntax",
    "```",
    "code",
    "program",
    "loop",
    "array",
    "recursion",
    "explain why",
    "write a ",
    "fix this",
)
ARTICLE_CHAR_CAP = 8_000
ATTACHMENT_CHAR_CAP = 12_000
MESSAGE_CHAR_CAP = 8_000
MERGED_MESSAGE_CHAR_CAP = MESSAGE_CHAR_CAP + ATTACHMENT_CHAR_CAP
MAX_MESSAGES = 24
XAI_CONTEXT_MESSAGES = 12
TOTAL_CHAR_CAP = 48_000
MAX_TOKENS_CAP = 2048

SYSTEM_PROMPT = """You are StoryKeep's school coding assistant for Steve — a personal RSS reader and student workspace.

Primary role:
- Help with school coding: explain concepts, debug logic, walk through assignments, and suggest approaches.
- When Steve asks for code, always use fenced markdown blocks with a language tag (```python, ```javascript, ```js, ```sql, ```text, etc.).
- Put runnable examples in fenced blocks, not bare pasted snippets, unless a one-word reference is enough.

Rules:
- Obsidian is paused; StoryKeep is the working archive. You cannot write to Steve's Surface Vault on disk. Saves go to StoryKeep DB rows only; backup is Export JSON / database dump to Backblaze.
- You cannot log into uCertify, scrape sites, or browse the live web.
- You cannot run tools, search X, generate images, or speak aloud.
- If Steve wants a reply kept, tell him to use Add to notes.
- Be concise, accurate, and useful for learning.
- Answer directly. Do not recap or quote the user's message unless they ask.
"""

RECAP_MODE_APPEND = """
Steve enabled "Recap my question" for this thread. You may briefly restate his question before answering when it helps clarity.
"""

ARTICLE_MODE_APPEND = """
Steve connected the current article. An excerpt is below.
- Ground answers in that excerpt when the question is about this article.
- Do not invent quotes or facts that are not supported by the excerpt.
- If Steve asks something outside the excerpt, you may use general knowledge and say clearly what is from the article vs general knowledge.
"""

GENERAL_MODE_APPEND = """
Steve disconnected the current article (or has no article open). You are in general-knowledge mode.
- Answer freely from your training: explain concepts, summarize topics, compare ideas, help with study questions, and give practical information.
- Do not refuse questions because no article is attached. Do not say you can only discuss the open article.
- You are not browsing the live web; if something needs up-to-the-minute data, say so briefly and still share what you know.
- If Steve later reconnects the article, you may use that excerpt when provided.
"""

ATTACHMENT_MODE_APPEND = """
Steve attached files to this turn.
- Prefer the extracted file text as source when the question is about those files.
- If an image is included as pixels in the latest user message, look at it. If you only have a filename, say so and do not invent the picture.
- Do not claim you received a raw upload you cannot read.
"""

_rate_lock = threading.Lock()
_rate_hits: dict[str, deque[float]] = defaultdict(deque)
_models_lock = threading.Lock()
_models_cache: tuple[float, set[str]] | None = None


def chat_url() -> str:
    url = (settings.xai_chat_url or "https://api.x.ai/v1/chat/completions").strip()
    return url or "https://api.x.ai/v1/chat/completions"


def key_format_ok() -> bool:
    key = (settings.xai_api_key or "").strip()
    return bool(key) and key.startswith("xai-")


def key_configured() -> bool:
    return key_format_ok()


def available_models() -> list[str]:
    raw = (settings.xai_chat_models or "").strip()
    if raw:
        models = [part.strip() for part in raw.split(",") if part.strip()]
        if models:
            return models
    full = (settings.xai_chat_model or "grok-4.6").strip()
    fast = (settings.xai_chat_fast_model or "grok-4-fast-non-reasoning").strip()
    ordered = [full]
    if fast and fast not in ordered:
        ordered.append(fast)
    return ordered


def default_full_model() -> str:
    models = available_models()
    preferred = (settings.xai_chat_model or "grok-4.6").strip()
    if preferred in models:
        return preferred
    return models[0]


def default_fast_model() -> str:
    preferred = (settings.xai_chat_fast_model or "grok-4-fast-non-reasoning").strip()
    models = available_models()
    if preferred in models:
        return preferred
    for candidate in models:
        if "fast" in candidate.lower():
            return candidate
    return models[-1] if len(models) > 1 else models[0]


def normalize_model_choice(choice: str | None) -> str:
    cleaned = (choice or MODEL_AUTO).strip()
    if not cleaned or cleaned.lower() == MODEL_AUTO:
        return MODEL_AUTO
    models = available_models()
    if cleaned not in models:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown model. Choose auto or one of: {', '.join(models)}.",
        )
    return cleaned


def pick_fast_for_auto(message: str, history: list[dict[str, str]] | None = None) -> bool:
    text = (message or "").strip()
    lower = text.lower()
    if len(text) > 180:
        return False
    if text.count("\n") >= 2:
        return False
    if any(keyword in lower for keyword in CODE_KEYWORDS):
        return False
    if history:
        for item in history[-4:]:
            prior = (item.get("content") or "").lower()
            if any(keyword in prior for keyword in CODE_KEYWORDS):
                return False
            if len(prior) > 240:
                return False
    return True


def resolve_model_for_request(choice: str, message: str, history: list[dict[str, str]] | None = None) -> str:
    normalized = normalize_model_choice(choice)
    if normalized != MODEL_AUTO:
        return normalized
    return default_fast_model() if pick_fast_for_auto(message, history) else default_full_model()


def model_label(choice: str, resolved: str | None = None) -> str:
    if choice == MODEL_AUTO:
        return f"Auto · {resolved}" if resolved else "Auto"
    return choice


def chat_error_message(status: int, detail: str) -> str:
    cleaned = (detail or "Unknown error.").strip()
    return f"Chat failed (HTTP {status}): {cleaned}"


def stream_error_event(status: int, detail: str, *, partial: bool = False) -> dict[str, object]:
    message = detail.strip() or "Unknown error."
    return {
        "error": chat_error_message(status, message),
        "message": message,
        "status": status,
        "detail": message,
        "partial": partial,
    }


def http_exception_detail(exc: HTTPException) -> tuple[int, str]:
    status_code = int(exc.status_code or 502)
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return status_code, detail


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


def require_key() -> str:
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


def _chat_timeout(*, streaming: bool) -> httpx.Timeout:
    if streaming:
        # No overall cap here — first byte is 8s, later silence uses the 8s read
        # timeout, and stream_completion enforces the 45s wall clock after tokens.
        return httpx.Timeout(
            timeout=None,
            connect=CHAT_CONNECT_TIMEOUT_SEC,
            read=CHAT_FIRST_BYTE_TIMEOUT_SEC,
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
    if status_code == 401:
        return HTTPException(status_code=401, detail="xAI auth failed")
    if status_code == 404:
        return HTTPException(status_code=400, detail=f"Invalid xAI model: {model}")
    if status_code == 400:
        return HTTPException(status_code=400, detail=cleaned)
    return HTTPException(status_code=502, detail=f"xAI HTTP {status_code}: {cleaned}")


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


def ping_xai() -> dict[str, object]:
    """One-token non-streaming probe for /chat/health."""
    key = require_key()
    model = default_fast_model()
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
        "max_tokens": 1,
        "temperature": 0,
    }
    started = time.perf_counter()
    try:
        with httpx.Client(timeout=_chat_timeout(streaming=False)) as client:
            response = client.post(chat_url(), json=payload, headers=_auth_headers(key))
            ms = int((time.perf_counter() - started) * 1000)
            xai_status = response.status_code
            if xai_status >= 400:
                detail = parse_xai_error_body(response.text, xai_status)
                if xai_status == 401:
                    detail = "xAI auth failed"
                logger.warning(
                    "xAI health ping HTTP %s model=%s ms=%s detail=%s",
                    xai_status,
                    model,
                    ms,
                    detail,
                )
                return {
                    "ok": False,
                    "model": model,
                    "ms": ms,
                    "xai_status": xai_status,
                    "message": detail,
                }
            logger.info("xAI health ping ok model=%s xai_status=%s ms=%s", model, xai_status, ms)
            return {"ok": True, "model": model, "ms": ms, "xai_status": xai_status}
    except httpx.HTTPError as exc:
        ms = int((time.perf_counter() - started) * 1000)
        detail = _transport_error_detail(exc)
        logger.warning("xAI health ping failed model=%s ms=%s detail=%s", model, ms, detail)
        return {"ok": False, "model": model, "ms": ms, "xai_status": None, "message": detail}


def enforce_rate_limit(user_id: UUID, now: float | None = None) -> None:
    limit = max(1, int(settings.chat_requests_per_hour or 120))
    window = 3600.0
    stamp = now if now is not None else time.time()
    key = str(user_id)
    with _rate_lock:
        hits = _rate_hits[key]
        while hits and stamp - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Chat limit is {limit} requests per hour. Try again later.",
            )
        hits.append(stamp)


def thread_window(messages: list[dict], limit: int = XAI_CONTEXT_MESSAGES) -> list[dict]:
    if len(messages) <= limit:
        return messages
    return messages[-limit:]


def drop_trailing_assistants(messages: list[dict]) -> list[dict]:
    """xAI payloads must end on the user turn (retry may have a partial assistant)."""
    cleaned = list(messages)
    while cleaned and (cleaned[-1].get("role") or "") != "user":
        cleaned.pop()
    return cleaned


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return " ".join(parts)
    return ""


def validate_payload(messages: list[dict]) -> list[dict]:
    if not messages:
        raise HTTPException(status_code=400, detail="Send at least one message.")
    if len(messages) > MAX_MESSAGES:
        raise HTTPException(status_code=400, detail="That conversation is too long. Start a new chat.")
    cleaned: list[dict] = []
    total = 0
    for item in messages:
        role = (item.get("role") or "").strip()
        if role not in {"user", "assistant"}:
            raise HTTPException(status_code=400, detail="Messages must be from user or assistant.")
        content = item.get("content")
        text = _content_text(content).strip()
        if isinstance(content, list):
            if not text and not any(isinstance(part, dict) and part.get("type") == "image_url" for part in content):
                raise HTTPException(status_code=400, detail="Empty messages are not allowed.")
            if len(text) > MERGED_MESSAGE_CHAR_CAP:
                raise HTTPException(status_code=400, detail="A message is too long.")
            total += len(text)
            cleaned.append({"role": role, "content": content})
            continue
        if not text:
            raise HTTPException(status_code=400, detail="Empty messages are not allowed.")
        if len(text) > MERGED_MESSAGE_CHAR_CAP:
            raise HTTPException(status_code=400, detail="A message is too long.")
        total += len(text)
        cleaned.append({"role": role, "content": text})
    if total > TOTAL_CHAR_CAP:
        raise HTTPException(status_code=400, detail="That chat payload is too large.")
    if cleaned[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="The last message must come from you.")
    return cleaned


def article_excerpt(article: Article, limit: int = ARTICLE_CHAR_CAP) -> str:
    body = (article.content_text or "").strip()
    if not body and article.content_html:
        body = _strip_tags(article.content_html)
    if not body:
        body = (article.summary or "").strip()
    if len(body) > limit:
        body = body[: limit - 1].rstrip() + "…"
    title = (article.title or "Untitled").strip()
    return f"Title: {title}\n\n{body}"


def build_xai_messages(
    history: list[dict],
    excerpt: str | None,
    *,
    include_article: bool,
    recap_question: bool = False,
    has_attachments: bool = False,
) -> list[dict]:
    if include_article and excerpt:
        system = SYSTEM_PROMPT + ARTICLE_MODE_APPEND + "\n\nCurrent article excerpt (truncated):\n" + excerpt
    else:
        system = SYSTEM_PROMPT + GENERAL_MODE_APPEND
    if recap_question:
        system += RECAP_MODE_APPEND
    if has_attachments:
        system += ATTACHMENT_MODE_APPEND
    windowed = thread_window(history)
    return [{"role": "system", "content": system}, *windowed]


def messages_for_xai(
    history: list[dict],
    *,
    model: str,
    db: Any = None,
    user: Any = None,
) -> list[dict]:
    from app.services.chat_attachments import merge_attachment_text, model_supports_vision, vision_parts

    windowed = thread_window(drop_trailing_assistants(history))
    vision = model_supports_vision(model) and db is not None and user is not None
    last = len(windowed) - 1
    prepared: list[dict] = []
    for index, item in enumerate(windowed):
        files = item.get("files") or []
        full = index == last and item.get("role") == "user"
        text = merge_attachment_text(item.get("content") or "", files, include_extracts=full)
        if full and vision and files:
            parts = vision_parts(db, user, files)
            if parts:
                prepared.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": text or "Steve attached an image."},
                            *parts,
                        ],
                    }
                )
                continue
        prepared.append({"role": item.get("role") or "user", "content": text})
    return prepared


def stream_completion(
    history: list[dict],
    excerpt: str | None,
    *,
    include_article: bool,
    recap_question: bool = False,
    model: str,
    model_choice: str = MODEL_AUTO,
    user_id: UUID | None = None,
    has_attachments: bool = False,
) -> Iterator[str]:
    key = require_key()
    validate_xai_model(model)
    latest_user = next((_content_text(item.get("content")) for item in reversed(history) if item.get("role") == "user"), "")
    logger.info(
        "xAI chat start model=%s choice=%s user=%s chars=%s",
        model,
        model_choice,
        user_id,
        len(latest_user or ""),
    )
    max_tokens = min(MAX_TOKENS_CAP, max(64, int(settings.xai_chat_max_tokens or MAX_TOKENS_CAP)))
    payload = {
        "model": model,
        "messages": build_xai_messages(
            history,
            excerpt,
            include_article=include_article,
            recap_question=recap_question,
            has_attachments=has_attachments,
        ),
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": 0.6,
    }
    started = time.perf_counter()
    first_byte_at: float | None = None
    first_event = threading.Event()
    yielded_any = False
    try:
        with httpx.Client(timeout=_chat_timeout(streaming=True)) as client:
            with client.stream(
                "POST",
                chat_url(),
                json=payload,
                headers=_auth_headers(key),
            ) as response:
                status_code = response.status_code
                if status_code >= 400:
                    body = response.read().decode("utf-8", errors="replace")
                    detail = parse_xai_error_body(body, status_code)
                    logger.warning(
                        "xAI chat HTTP %s model=%s ttfb=%.2fs detail=%s",
                        status_code,
                        model,
                        time.perf_counter() - started,
                        detail,
                    )
                    raise map_xai_http_error(status_code, detail, model)

                remaining = CHAT_FIRST_BYTE_TIMEOUT_SEC - (time.perf_counter() - started)
                if remaining <= 0:
                    raise HTTPException(status_code=504, detail=XAI_SILENT_DETAIL)

                def _kill_if_silent() -> None:
                    if not first_event.is_set():
                        try:
                            response.close()
                        except Exception:
                            pass

                watchdog = threading.Timer(remaining, _kill_if_silent)
                watchdog.daemon = True
                watchdog.start()
                try:
                    for line in response.iter_lines():
                        elapsed = time.perf_counter() - started
                        if first_byte_at is None and elapsed >= CHAT_FIRST_BYTE_TIMEOUT_SEC:
                            raise HTTPException(status_code=504, detail=XAI_SILENT_DETAIL)
                        if first_byte_at is not None and elapsed >= CHAT_STREAM_TIMEOUT_SEC:
                            raise HTTPException(
                                status_code=504,
                                detail=f"Chat timed out after {int(CHAT_STREAM_TIMEOUT_SEC)}s.",
                            )
                        if not line:
                            continue
                        if line.startswith("data:"):
                            data = line[5:].strip()
                        else:
                            data = line.strip()
                        if data == "[DONE]":
                            break
                        text, active = _parse_sse_chunk(data)
                        if active and first_byte_at is None:
                            first_byte_at = time.perf_counter()
                            first_event.set()
                            watchdog.cancel()
                            logger.info(
                                "xAI chat first_byte model=%s status=%s ttfb=%.2fs user=%s",
                                model,
                                status_code,
                                first_byte_at - started,
                                user_id,
                            )
                        if not active:
                            continue
                        if text:
                            yielded_any = True
                            yield text
                    if first_byte_at is None:
                        raise HTTPException(status_code=504, detail=XAI_SILENT_DETAIL)
                finally:
                    first_event.set()
                    watchdog.cancel()
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        elapsed = time.perf_counter() - started
        silent = first_byte_at is None or not yielded_any
        if silent:
            detail = XAI_SILENT_DETAIL
            status_code = 504 if isinstance(exc, (httpx.ReadTimeout, httpx.TimeoutException)) or elapsed >= CHAT_FIRST_BYTE_TIMEOUT_SEC else 502
            if status_code == 502:
                detail = _transport_error_detail(exc)
            logger.warning(
                "xAI chat transport error model=%s user=%s ttfb=%.2fs detail=%s",
                model,
                user_id,
                elapsed,
                detail,
            )
            raise HTTPException(status_code=status_code, detail=detail) from exc
        logger.warning(
            "xAI chat transport error after tokens model=%s user=%s elapsed=%.2fs detail=%s",
            model,
            user_id,
            elapsed,
            exc,
        )
        raise HTTPException(
            status_code=504,
            detail=f"Chat timed out after {int(CHAT_STREAM_TIMEOUT_SEC)}s.",
        ) from exc
    except Exception as exc:
        elapsed = time.perf_counter() - started
        if first_byte_at is None or not yielded_any:
            raise HTTPException(status_code=504, detail=XAI_SILENT_DETAIL) from exc
        logger.warning(
            "xAI chat stopped after tokens model=%s user=%s elapsed=%.2fs detail=%s",
            model,
            user_id,
            elapsed,
            exc,
        )
        raise HTTPException(
            status_code=504,
            detail=f"Chat timed out after {int(CHAT_STREAM_TIMEOUT_SEC)}s.",
        ) from exc


def _parse_sse_chunk(raw: str) -> tuple[str, bool]:
    """Return (user-visible text, whether xAI sent any token activity)."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return "", False
    choices = parsed.get("choices") or []
    if not choices:
        return "", False
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    visible = content if isinstance(content, str) and content else ""
    if not visible:
        message = choices[0].get("message") or {}
        fallback = message.get("content")
        if isinstance(fallback, str) and fallback:
            visible = fallback
    reasoning = delta.get("reasoning_content")
    if not visible and isinstance(reasoning, str) and reasoning:
        visible = reasoning
    active = bool(visible) or (isinstance(reasoning, str) and bool(reasoning))
    return visible, active


def _delta_text(raw: str) -> str:
    text, _ = _parse_sse_chunk(raw)
    return text


def _strip_tags(html: str) -> str:
    import re

    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()
