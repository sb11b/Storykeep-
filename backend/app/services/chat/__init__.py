"""Chat service package — decomposed from the monolithic chat.py (2,097 lines).

All public names are re-exported here so existing imports like
``from app.services.chat import X`` and ``from app.services import chat`` continue
to work unchanged.
"""
from __future__ import annotations

# --- Constants and shared helpers (from _shared) ---
from ._shared import (
    ARTICLE_CHAR_CAP,
    AUTO_LOW_MAX_CHARS,
    CHAT_CONNECT_TIMEOUT_SEC,
    CHAT_FIRST_BYTE_TIMEOUT_HEAVY_SEC,
    CHAT_FIRST_BYTE_TIMEOUT_MAX_SEC,
    CHAT_FIRST_BYTE_TIMEOUT_SEC,
    CHAT_HEALTH_TIMEOUT_SEC,
    CHAT_IDLE_AFTER_TOKEN_MAX_SEC,
    CHAT_IDLE_AFTER_TOKEN_MIN_SEC,
    CHAT_STREAM_TIMEOUT_SEC,
    CODE_KEYWORDS,
    CURRENT_CHAT_MODEL,
    CURRENT_FAST_MODEL,
    DEFAULT_REASONING_EFFORT,
    EMPTY_REPLY_FALLBACK,
    JUNIOR_MAX_RESPONSE_WORDS,
    MAX_MESSAGES,
    MAX_TOKENS_CAP,
    MERGED_MESSAGE_CHAR_CAP,
    MESSAGE_CHAR_CAP,
    MODEL_AUTO,
    OPTIONAL_CHAT_MODELS,
    REASONING_AUTO,
    REASONING_EFFORTS,
    SEND_CONTEXT_CHAR_CAP,
    SEND_CONTEXT_TOO_LARGE,
    SEND_THREAD_TOO_LARGE,
    SSE_PADDING,
    STREAM_HEARTBEAT,
    TOTAL_CHAR_CAP,
    XAI_CONTEXT_MESSAGES,
    XAI_EMPTY_DETAIL,
    XAI_MODELS_CACHE_SEC,
    XAI_SILENT_DETAIL,
    _ANALYZE_RE,
    _CHARS_PER_WORD_EST,
    _CLINE_RESULT_RE,
    _DEAD_MODEL_ALIASES,
    _FILE_PATH_RE,
    _LEGACY_MAX_TOKEN_PINS,
    _SCHOOL_CODE_RE,
    _SEQ_NUMBER_RE,
    _SMALL_TALK_RE,
    _SYSTEM_OVERHEAD_RESERVE,
    _THREAD_TRIM_ASSISTANT,
    _THREAD_TRIM_MIN,
    _THREAD_TRIM_TARGET,
    _THREAD_TRIM_USER,
    _WORKING_NOTE_STREAM_MIN,
    _WRITE_CLINE_PROMPT_RE,
    _XAI_COMBINED_CHAR_CAP,
    _clip_text,
    _content_text,
    _models_cache,
    _models_lock,
    _rate_hits,
    _rate_lock,
    _strip_tags,
    article_body_text,
    chat_idle_after_token_sec,
    chat_idle_timeout_detail,
    resolved_max_output_tokens,
)

# --- Model routing ---
from .model_routing import (
    _canopy_enabled,
    _dedupe_models,
    _is_cursor_start_explicit,
    _with_optional_models,
    attach_reasoning_effort,
    available_models,
    clamp_reasoning_effort,
    default_fast_model,
    default_full_model,
    is_short_chat,
    is_small_talk_turn,
    model_label,
    model_uses_reasoning,
    normalize_model_choice,
    normalize_reasoning_effort,
    pace_reason,
    pace_why,
    pick_fast_for_auto,
    pick_xhigh_for_auto,
    posted_spend_label,
    resolve_model_for_request,
    resolve_reasoning_for_request,
    rewrite_xai_model,
    should_attach_chat_tools,
    should_attach_working_note,
)

# --- HTTP transport / auth / error mapping ---
from ._http import (
    _auth_headers,
    _chat_timeout,
    _transport_error_detail,
    _xai_key,
    _xai_responses_url,
    _xai_ttft_log,
    chat_url,
    fetch_xai_model_ids,
    first_byte_timeout_sec,
    key_configured,
    key_format_ok,
    map_xai_http_error,
    parse_xai_error_body,
    require_key,
    responses_url,
    validate_xai_model,
)

# --- System prompt construction ---
from .system_prompt import (
    ARTICLE_MODE_APPEND,
    ATTACHMENT_MODE_APPEND,
    GENERAL_MODE_APPEND,
    NOTE_MODE_APPEND,
    RECAP_MODE_APPEND,
    SYSTEM_PROMPT,
    WORKING_NOTE_MODE_APPEND,
    _load_doc,
    _load_junior_system,
    build_system_content,
)

# --- Streaming / SSE ---
from .streaming import (
    _anext_or_none,
    _delta_text,
    _parse_sse_chunk,
    _parse_sse_payload,
    _strip_canopy_tool_markup,
    chat_error_message,
    encode_sse,
    http_exception_detail,
    is_recoverable_empty_reply,
    pace_stream,
    ping_xai,
    stream_completion,
    stream_error_event,
)

# --- Attachments / message building ---
from .attachments import (
    _clip_message_content,
    _trim_prepared_for_cap,
    article_excerpt,
    build_xai_messages,
    cap_working_excerpt,
    drop_trailing_assistants,
    latest_user_files,
    messages_char_count,
    messages_for_xai,
    reject_oversized_send,
    send_context_chars,
    slim_history_for_retry,
    thread_trim_cap,
    thread_window,
    validate_payload,
)

# --- Tools / completions ---
from .tools import (
    COMPLETIONS_ALLOWED_TOOL_TYPES,
    RESPONSES_CODE_TOOL_TYPES,
    RESPONSES_SEARCH_TOOL_TYPES,
    _CANT_SEARCH,
    build_chat_completions_payload,
    complete_once,
    complete_with_code_execution,
    complete_with_code_interpreter,
    complete_with_server_tools,
    complete_with_web_search,
    filter_completions_tools,
    parse_responses_text,
    responses_used_search,
    wants_responses_search,
)

# --- Rate limiting ---
from .rate_limit import enforce_rate_limit

# Re-export settings and httpx so mock.patch("app.services.chat.settings") etc. still work
from app.config import settings
import httpx

__all__ = [
    # ... all public names are available via star-import or direct import ...
]
