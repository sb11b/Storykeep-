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

XAI_CHAT_URL = "https://api.x.ai/v1/chat/completions"
ARTICLE_CHAR_CAP = 12_000
MESSAGE_CHAR_CAP = 8_000
MAX_MESSAGES = 24
TOTAL_CHAR_CAP = 48_000
MAX_TOKENS_CAP = 2048

SYSTEM_PROMPT = """You are StoryKeep's reader assistant. You help Steve think about articles, papers, and notes in his personal archive.

Rules:
- You cannot overwrite Obsidian originals (Steve's Surface Vault). Saves go to StoryKeep notes and the downloadable overlay pack (StoryKeep/Additions).
- You cannot log into uCertify, scrape sites, or browse the live web.
- You cannot run tools, search X, generate images, or speak.
- If Steve wants a reply kept, tell him to use Add to notes. That creates a StoryKeep overlay addition (StoryKeep/Additions), never a vault overwrite.
- Be concise and useful. Use the article excerpt when it is provided; do not invent quotes that are not in it.
- If no article is attached, answer from general knowledge and the conversation, and say when you lack archive context.
"""

_rate_lock = threading.Lock()
_rate_hits: dict[str, deque[float]] = defaultdict(deque)


def key_configured() -> bool:
    return bool((settings.xai_api_key or "").strip())


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


def build_xai_messages(history: list[dict[str, str]], excerpt: str | None) -> list[dict[str, str]]:
    system = SYSTEM_PROMPT
    if excerpt:
        system += "\n\nCurrent article excerpt (truncated):\n" + excerpt
    return [{"role": "system", "content": system}, *history]


def stream_completion(history: list[dict[str, str]], excerpt: str | None) -> Iterator[str]:
    key = require_key()
    model = (settings.xai_chat_model or "grok-4").strip()
    max_tokens = min(MAX_TOKENS_CAP, max(64, int(settings.xai_chat_max_tokens or MAX_TOKENS_CAP)))
    payload = {
        "model": model,
        "messages": build_xai_messages(history, excerpt),
        "stream": True,
        "max_tokens": max_tokens,
        "temperature": 0.6,
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        with httpx.Client(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
            with client.stream("POST", XAI_CHAT_URL, json=payload, headers=headers) as response:
                if response.status_code >= 400:
                    detail = response.read().decode("utf-8", errors="replace")[:400]
                    logger.warning("xAI chat error %s: %s", response.status_code, detail)
                    raise HTTPException(
                        status_code=502,
                        detail="Grok did not return a reply. Check XAI_API_KEY and XAI_CHAT_MODEL on Railway.",
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
        raise HTTPException(status_code=504, detail="Grok timed out.") from exc
    except httpx.HTTPError as exc:
        logger.exception("xAI chat request failed")
        raise HTTPException(status_code=502, detail="Could not reach xAI chat.") from exc


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
