from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException, status

from app.config import settings
from app.models import Article
from app.services.chat_attachments import ATTACHMENT_CHAR_CAP

logger = logging.getLogger(__name__)

MODEL_AUTO = "auto"
REASONING_AUTO = "auto"
CURRENT_CHAT_MODEL = "grok-4.6"
CURRENT_FAST_MODEL = "grok-4.3"
# Selectable, never the Auto default. Kept even if XAI_CHAT_MODELS omits it.
OPTIONAL_CHAT_MODELS = ("grok-4.7",)
REASONING_EFFORTS = ("low", "medium", "high", "xhigh")
DEFAULT_REASONING_EFFORT = "low"
CHAT_STREAM_TIMEOUT_SEC = 45.0
CHAT_CONNECT_TIMEOUT_SEC = 8.0
CHAT_FIRST_BYTE_TIMEOUT_SEC = 45.0
CHAT_FIRST_BYTE_TIMEOUT_HEAVY_SEC = 60.0
CHAT_FIRST_BYTE_TIMEOUT_MAX_SEC = 90.0
CHAT_IDLE_AFTER_TOKEN_MIN_SEC = 120.0
CHAT_IDLE_AFTER_TOKEN_MAX_SEC = 7200.0
CHAT_HEALTH_TIMEOUT_SEC = 10.0
XAI_SILENT_DETAIL = "xAI silent"
XAI_EMPTY_DETAIL = "Junior returned no text for this turn."
EMPTY_REPLY_FALLBACK = (
    "I didn't get a text reply from the model on that turn. "
    "Try sending again — if it keeps happening, start a fresh chat thread."
)


STREAM_HEARTBEAT = object()


SSE_PADDING = b":" + (b" " * 4096) + b"\n\n"
# Railway env can still hold retired aliases. Invalid ids hang the stream until a proxy 504.
_DEAD_MODEL_ALIASES = {
    "grok-4-fast-non-reasoning": CURRENT_FAST_MODEL,
    "grok-4-fast": CURRENT_FAST_MODEL,
    "grok-4-fast-reasoning": CURRENT_CHAT_MODEL,
    "grok-4-1-fast": CURRENT_FAST_MODEL,
    "grok-4-1-fast-non-reasoning": CURRENT_FAST_MODEL,
    "grok-4-1-fast-reasoning": CURRENT_CHAT_MODEL,
    "grok-4.20-0309-non-reasoning": CURRENT_FAST_MODEL,
    "grok-4.20-0309-reasoning": CURRENT_CHAT_MODEL,
    "grok-4": CURRENT_CHAT_MODEL,
    "grok-3": CURRENT_CHAT_MODEL,
    "grok-3-mini": CURRENT_FAST_MODEL,
}
XAI_MODELS_CACHE_SEC = 900.0
AUTO_LOW_MAX_CHARS = 400
# Auto: hello / small talk / a short paste → grok-4.6 · low.
# xhigh only for school, code, or a long analyze turn.
_SMALL_TALK_RE = re.compile(
    r"^(?:hi|hello|hey|yo|thanks|thank you|"
    r"good (?:morning|afternoon|evening|night)|"
    r"how(?:'s| is| was| were)? (?:it going|your (?:morning|day|evening|night)|you)|"
    r"what(?:'s| is|s) up)[\s!?.]*$",
    re.I,
)
_ANALYZE_RE = re.compile(r"\banaly[sz]e\b", re.I)
CODE_KEYWORDS = (
    "code",
    "debug",
    "rewrite paper",
    "homework",
    "assignment",
    "algorithm",
    "python",
    "javascript",
    "typescript",
)
_SCHOOL_CODE_RE = re.compile(
    r"```|"
    r"\b(?:python|javascript|typescript|homework|assignment|algorithm|"
    r"debug|schoolwork|rewrite paper|linked list|dat[- ]?\d+|code)\b|"
    r"\b(?:function|class)\s+\w+",
    re.I,
)

# Patterns that should NOT trigger xhigh unless Steve explicitly says to start the agent.
_SEQ_NUMBER_RE = re.compile(
    r"\bsequenc(?:e|ed)\s+(?:number\s+)?#?\s*"
    r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|twenty-one|twenty-two|twenty-three|twenty-four|twenty-five|twenty-six|twenty-seven|twenty-eight|twenty-nine|thirty)\b"
    r"|\b(?:sequenced\s+)?#\s*(\d+)\b",
    re.I,
)
_WRITE_CLINE_PROMPT_RE = re.compile(r"\bwrite\s+a\s+cline\s+prompt\b", re.I)
_FILE_PATH_RE = re.compile(r"\b[\w/\\.-]+\.(?:py|tsx?|ts|js|md|sql)\b", re.I)
_CLINE_RESULT_RE = re.compile(r"\bcline\s+(?:returned|result|output|said)\b|\bresult\s+from\s+cline\b", re.I)
ARTICLE_CHAR_CAP = 10_000
MESSAGE_CHAR_CAP = 24_000
MERGED_MESSAGE_CHAR_CAP = MESSAGE_CHAR_CAP + ATTACHMENT_CHAR_CAP
MAX_MESSAGES = 24
XAI_CONTEXT_MESSAGES = 12
# Room for a 100+ page attachment plus the thread. The old 120k total clipped those extracts.
TOTAL_CHAR_CAP = 800_000
SEND_CONTEXT_CHAR_CAP = 800_000
_XAI_COMBINED_CHAR_CAP = 900_000
_THREAD_TRIM_TARGET = 760_000
_THREAD_TRIM_MIN = 32_000
_WORKING_NOTE_STREAM_MIN = 8_000
SEND_CONTEXT_TOO_LARGE = "This turn is over the cap. Include a heading, a selection, or the next chunk."
SEND_THREAD_TOO_LARGE = "This thread slice is too long. Shorten your message or start a new chat."
_THREAD_TRIM_ASSISTANT = 1_200
_THREAD_TRIM_USER = 800
_SYSTEM_OVERHEAD_RESERVE = 12_000
JUNIOR_MAX_RESPONSE_WORDS = 100_000
_CHARS_PER_WORD_EST = 5
MAX_TOKENS_CAP = (JUNIOR_MAX_RESPONSE_WORDS * _CHARS_PER_WORD_EST + 3) // 4


_LEGACY_MAX_TOKEN_PINS = frozenset({700, 900, 1200, 2048, 4096, 8192})


# --- Module-level mutable state (shared across submodules via this package) ---

_rate_lock = threading.Lock()
_rate_hits: dict[str, deque] = defaultdict(deque)
_models_lock = threading.Lock()
_models_cache: tuple[float, set[str]] | None = None


# --- Token / timeout helpers ---

def resolved_max_output_tokens() -> int:
    """~100k words at ~1.25 tokens/word. Override with XAI_CHAT_MAX_TOKENS."""
    raw = int(settings.xai_chat_max_tokens or MAX_TOKENS_CAP)
    # Railway/env pins from older deploys (2048) must not block the word cap.
    if raw in _LEGACY_MAX_TOKEN_PINS or raw < 16_000:
        raw = MAX_TOKENS_CAP
    return min(MAX_TOKENS_CAP, max(64, raw))


def chat_idle_after_token_sec(max_tokens: int | None = None) -> float:
    """Scale idle window for long completions so streams are not cut at 60s."""
    budget = max(64, int(max_tokens or resolved_max_output_tokens()))
    return min(
        CHAT_IDLE_AFTER_TOKEN_MAX_SEC,
        max(CHAT_IDLE_AFTER_TOKEN_MIN_SEC, budget / 40.0),
    )


def chat_idle_timeout_detail(max_tokens: int | None = None) -> str:
    secs = int(chat_idle_after_token_sec(max_tokens))
    if secs >= 3600:
        return f"Timed out after {secs // 60} minutes waiting for the next token."
    return f"Timed out after {secs}s waiting for the next token."


# --- Text helpers (used by attachments, streaming, tools) ---

def _content_text(value: Any) -> str:
    """Accept string, text-part arrays, and {text|content|output_text} objects."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_content_text(item) for item in value)
    if isinstance(value, dict):
        for key in ("text", "content", "output_text"):
            piece = value.get(key)
            if isinstance(piece, str) and piece:
                return piece
            if isinstance(piece, list):
                joined = _content_text(piece)
                if joined:
                    return joined
    return ""


def _strip_tags(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _clip_text(text: str, cap: int) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= cap:
        return cleaned
    cut = cleaned[: max(cap - 1, 0)].rstrip()
    return f"{cut}…" if cut else "…"


def article_body_text(article: Article) -> str:
    body = (article.content_text or "").strip()
    if not body and article.content_html:
        body = _strip_tags(article.content_html)
    if not body:
        body = (article.summary or "").strip()
    return body
