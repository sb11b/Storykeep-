from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from typing import Iterator
from uuid import UUID

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.models import Article

logger = logging.getLogger(__name__)

MODEL_AUTO = "auto"
XAI_CHAT_URL = "https://api.x.ai/v1/chat/completions"
CHAT_STREAM_TIMEOUT_SEC = 90.0
CHAT_CONNECT_TIMEOUT_SEC = 15.0
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
ARTICLE_CHAR_CAP = 12_000
MESSAGE_CHAR_CAP = 8_000
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

_rate_lock = threading.Lock()
_rate_hits: dict[str, deque[float]] = defaultdict(deque)


def key_configured() -> bool:
    return bool((settings.xai_api_key or "").strip())


def available_models() -> list[str]:
    raw = (settings.xai_chat_models or "").strip()
    if raw:
        models = [part.strip() for part in raw.split(",") if part.strip()]
        if models:
            return models
    full = (settings.xai_chat_model or "grok-4").strip()
    fast = (settings.xai_chat_fast_model or "grok-4-fast").strip()
    ordered = [full]
    if fast and fast not in ordered:
        ordered.append(fast)
    return ordered


def default_full_model() -> str:
    models = available_models()
    preferred = (settings.xai_chat_model or "grok-4").strip()
    if preferred in models:
        return preferred
    return models[0]


def default_fast_model() -> str:
    preferred = (settings.xai_chat_fast_model or "grok-4-fast").strip()
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
    return {
        "error": chat_error_message(status, detail),
        "status": status,
        "detail": detail.strip() or "Unknown error.",
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
    return key


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


def thread_window(messages: list[dict[str, str]], limit: int = XAI_CONTEXT_MESSAGES) -> list[dict[str, str]]:
    if len(messages) <= limit:
        return messages
    return messages[-limit:]


def validate_payload(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    if not messages:
        raise HTTPException(status_code=400, detail="Send at least one message.")
    if len(messages) > MAX_MESSAGES:
        raise HTTPException(status_code=400, detail="That conversation is too long. Start a new chat.")
    cleaned: list[dict[str, str]] = []
    total = 0
    for item in messages:
        role = (item.get("role") or "").strip()
        if role not in {"user", "assistant"}:
            raise HTTPException(status_code=400, detail="Messages must be from user or assistant.")
        content = (item.get("content") or "").strip()
        if not content:
            raise HTTPException(status_code=400, detail="Empty messages are not allowed.")
        if len(content) > MESSAGE_CHAR_CAP:
            raise HTTPException(status_code=400, detail="A message is too long.")
        total += len(content)
        cleaned.append({"role": role, "content": content})
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


def build_xai_messages(history: list[dict[str, str]], excerpt: str | None, *, include_article: bool) -> list[dict[str, str]]:
    if include_article and excerpt:
        system = SYSTEM_PROMPT + ARTICLE_MODE_APPEND + "\n\nCurrent article excerpt (truncated):\n" + excerpt
    else:
        system = SYSTEM_PROMPT + GENERAL_MODE_APPEND
    windowed = thread_window(history)
    return [{"role": "system", "content": system}, *windowed]


def stream_completion(
    history: list[dict[str, str]],
    excerpt: str | None,
    *,
    include_article: bool,
    model: str,
    model_choice: str = MODEL_AUTO,
    user_id: UUID | None = None,
) -> Iterator[str]:
    key = require_key()
    latest_user = next((item["content"] for item in reversed(history) if item.get("role") == "user"), "")
    logger.info(
        "xAI chat model=%s choice=%s user=%s chars=%s",
        model,
        model_choice,
        user_id,
        len(latest_user),
    )
    max_tokens = min(MAX_TOKENS_CAP, max(64, int(settings.xai_chat_max_tokens or MAX_TOKENS_CAP)))
    payload = {
        "model": model,
        "messages": build_xai_messages(history, excerpt, include_article=include_article),
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": 0.6,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(
            timeout=httpx.Timeout(CHAT_STREAM_TIMEOUT_SEC, connect=CHAT_CONNECT_TIMEOUT_SEC),
        ) as client:
            with client.stream("POST", XAI_CHAT_URL, json=payload, headers=headers) as response:
                if response.status_code >= 400:
                    body = response.read().decode("utf-8", errors="replace")
                    detail = parse_xai_error_body(body, response.status_code)
                    logger.warning("xAI chat HTTP %s model=%s: %s", response.status_code, model, detail)
                    raise HTTPException(
                        status_code=502,
                        detail=f"xAI HTTP {response.status_code}: {detail}",
                    )
                for line in response.iter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data = line[5:].strip()
                    else:
                        data = line.strip()
                    if data == "[DONE]":
                        break
                    text = _delta_text(data)
                    if text:
                        yield text
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        logger.warning(
            "xAI chat timed out after %.0fs model=%s user=%s",
            CHAT_STREAM_TIMEOUT_SEC,
            model,
            user_id,
        )
        raise HTTPException(
            status_code=504,
            detail=f"Grok timed out after {int(CHAT_STREAM_TIMEOUT_SEC)}s.",
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("xAI chat transport error model=%s user=%s: %s", model, user_id, exc)
        raise HTTPException(status_code=502, detail=f"Could not reach xAI chat: {exc}") from exc


def _delta_text(raw: str) -> str:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    choices = parsed.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    if isinstance(content, str):
        return content
    message = choices[0].get("message") or {}
    fallback = message.get("content")
    return fallback if isinstance(fallback, str) else ""


def _strip_tags(html: str) -> str:
    import re

    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()
