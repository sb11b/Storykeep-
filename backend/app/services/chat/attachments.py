from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

from app.services.chat_attachments import ATTACHMENT_CHAR_CAP
from app.services.include_chunk import (
    INCLUDE_TURN_CHAR_CAP,
    format_excerpt as format_include_excerpt,
    resolve_include_slice,
)

from ._shared import (
    MERGED_MESSAGE_CHAR_CAP,
    MAX_MESSAGES,
    SEND_CONTEXT_TOO_LARGE,
    SEND_THREAD_TOO_LARGE,
    TOTAL_CHAR_CAP,
    _SYSTEM_OVERHEAD_RESERVE,
    _THREAD_TRIM_ASSISTANT,
    _THREAD_TRIM_MIN,
    _THREAD_TRIM_TARGET,
    _THREAD_TRIM_USER,
    _WORKING_NOTE_STREAM_MIN,
    _XAI_COMBINED_CHAR_CAP,
    XAI_CONTEXT_MESSAGES,
    _content_text,
    _clip_text,
    _strip_tags,
    article_body_text,
)
from .model_routing import should_attach_chat_tools, should_attach_working_note
from .system_prompt import SYSTEM_PROMPT, build_system_content

logger = logging.getLogger(__name__)


def thread_window(messages: list[dict], limit: int | None = None) -> list[dict]:
    if limit is None:
        limit = XAI_CONTEXT_MESSAGES
    if len(messages) <= limit:
        return messages
    return messages[-limit:]


def drop_trailing_assistants(messages: list[dict]) -> list[dict]:
    """xAI payloads must end on the user turn (retry may have a partial assistant)."""
    cleaned = list(messages)
    while cleaned and (cleaned[-1].get("role") or "") != "user":
        cleaned.pop()
    return cleaned


def messages_char_count(messages: list[dict]) -> int:
    return sum(len(_content_text(item.get("content"))) for item in messages)


def _clip_message_content(content: Any, cap: int) -> Any:
    if isinstance(content, str):
        return _clip_text(content, cap)
    if isinstance(content, list):
        clipped: list[Any] = []
        remaining = cap
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "image_url":
                clipped.append(part)
                continue
            if part.get("type") != "text":
                clipped.append(part)
                continue
            text = str(part.get("text") or "")
            if len(text) <= remaining:
                clipped.append(part)
                remaining = max(0, remaining - len(text))
                continue
            clipped.append({**part, "text": _clip_text(text, remaining)})
            remaining = 0
            break
        return clipped
    return content


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
                content = _clip_message_content(content, MERGED_MESSAGE_CHAR_CAP)
                text = _content_text(content).strip()
            total += len(text)
            cleaned.append({"role": role, "content": content})
            continue
        if not text:
            raise HTTPException(status_code=400, detail="Empty messages are not allowed.")
        if len(text) > MERGED_MESSAGE_CHAR_CAP:
            text = _clip_text(text, MERGED_MESSAGE_CHAR_CAP)
        total += len(text)
        cleaned.append({"role": role, "content": text})
    if total > TOTAL_CHAR_CAP:
        raise HTTPException(status_code=413, detail=SEND_THREAD_TOO_LARGE)
    if cleaned[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="The last message must come from you.")
    return cleaned


def thread_trim_cap(*, system_overhead: int = 0) -> int:
    """Reserve room in the xAI window for system prompt slices and memory."""
    overhead = min(max(0, int(system_overhead)), 80_000)
    shaved = _SYSTEM_OVERHEAD_RESERVE + overhead // 4
    return max(_THREAD_TRIM_MIN, _THREAD_TRIM_TARGET - shaved)


def cap_working_excerpt(
    working_excerpt: str | None,
    *,
    thread_chars: int,
    include_chars: int = 0,
) -> str | None:
    """Keep thread + attachment context; shrink the working-note slice if needed."""
    text = (working_excerpt or "").strip()
    if not text:
        return None
    budget = _XAI_COMBINED_CHAR_CAP - max(0, int(thread_chars)) - max(0, int(include_chars)) - _SYSTEM_OVERHEAD_RESERVE
    limit = max(_WORKING_NOTE_STREAM_MIN, budget)
    if len(text) <= limit:
        return text
    return _clip_text(text, limit)


def _trim_prepared_for_cap(prepared: list[dict], cap: int) -> list[dict]:
    """Drop chars from oldest turns, then clip the latest user turn if needed."""
    trimmed = [dict(item) for item in prepared]
    while messages_char_count(trimmed) > cap and len(trimmed) > 1:
        cut = False
        for index in range(len(trimmed) - 1):
            item = trimmed[index]
            if item.get("role") != "assistant":
                continue
            text = _content_text(item.get("content"))
            if len(text) <= _THREAD_TRIM_ASSISTANT:
                continue
            trimmed[index] = {**item, "content": _clip_text(text, _THREAD_TRIM_ASSISTANT)}
            cut = True
            break
        if cut:
            continue
        for index in range(len(trimmed) - 1):
            item = trimmed[index]
            if item.get("role") != "user":
                continue
            text = _content_text(item.get("content"))
            if len(text) <= _THREAD_TRIM_USER:
                continue
            trimmed[index] = {**item, "content": _clip_text(text, _THREAD_TRIM_USER)}
            cut = True
            break
        if cut:
            continue
        last = trimmed[-1]
        text = _content_text(last.get("content"))
        if len(text) > MERGED_MESSAGE_CHAR_CAP:
            trimmed[-1] = {**last, "content": _clip_message_content(last.get("content"), MERGED_MESSAGE_CHAR_CAP)}
            cut = True
        if not cut:
            break
    return trimmed


def slim_history_for_retry(history: list[dict]) -> list[dict]:
    """Second-chance payload: keep the latest user turn, drop older bulk."""
    return _trim_prepared_for_cap(history, _THREAD_TRIM_MIN)


def send_context_chars(
    history: list[dict],
    *,
    article_body: str | None = None,
    note_body: str | None = None,
    model: str = "grok-4.6",
) -> int:
    prepared = messages_for_xai(history, model=model)
    total = messages_char_count(prepared)
    if article_body:
        total += len(article_body)
    if note_body and note_body != article_body:
        total += len(note_body)
    return total


def reject_oversized_send(
    history: list[dict],
    *,
    article_body: str | None = None,
    note_body: str | None = None,
    working_excerpt: str | None = None,
    system_overhead: int = 0,
) -> None:
    overhead = max(0, int(system_overhead))
    prepared = messages_for_xai(
        history,
        model="grok-4.6",
        trim_cap=thread_trim_cap(system_overhead=overhead),
    )
    thread_chars = messages_char_count(prepared)
    include_chars = len(article_body or "")
    if note_body and note_body != article_body:
        include_chars += len(note_body)
    working_chars = len(working_excerpt or "")
    combined = thread_chars + include_chars + working_chars
    if not article_body and not note_body:
        if combined > _XAI_COMBINED_CHAR_CAP:
            raise HTTPException(status_code=413, detail=SEND_THREAD_TOO_LARGE)
        return
    if include_chars > INCLUDE_TURN_CHAR_CAP:
        raise HTTPException(status_code=413, detail=SEND_CONTEXT_TOO_LARGE)
    if combined > _XAI_COMBINED_CHAR_CAP:
        raise HTTPException(status_code=413, detail=SEND_CONTEXT_TOO_LARGE)


def article_excerpt(article, limit: int = INCLUDE_TURN_CHAR_CAP) -> str:
    del limit  # slices are capped by INCLUDE_TURN_CHAR_CAP
    body = article_body_text(article)
    html = getattr(article, "content_html", None)
    slice = resolve_include_slice(
        body,
        mode="chunk",
        title=article.title,
        html=html if isinstance(html, str) else None,
    )
    return format_include_excerpt((article.title or "Untitled").strip(), slice)


def build_xai_messages(
    history: list[dict],
    excerpt: str | None,
    *,
    include_article: bool,
    recap_question: bool = False,
    has_attachments: bool = False,
    include_note: bool = False,
    note_excerpt: str | None = None,
    working_excerpt: str | None = None,
    extra_system: str | None = None,
    thread_limit: int | None = None,
) -> list[dict]:
    system = build_system_content(
        excerpt,
        include_article=include_article,
        recap_question=recap_question,
        has_attachments=has_attachments,
        include_note=include_note,
        note_excerpt=note_excerpt,
        working_excerpt=working_excerpt,
        extra_system=extra_system,
    )
    windowed = thread_window(history, limit=thread_limit if thread_limit is not None else XAI_CONTEXT_MESSAGES)
    return [{"role": "system", "content": system}, *windowed]


def messages_for_xai(
    history: list[dict],
    *,
    model: str,
    db: Any = None,
    user: Any = None,
    trim_cap: int | None = None,
) -> list[dict]:
    from app.services import junior_model
    from app.services.chat_attachments import merge_attachment_text, model_supports_vision, vision_parts

    windowed = thread_window(
        drop_trailing_assistants(history),
        limit=junior_model.JUNIOR_THREAD_WINDOW,
    )
    vision = model_supports_vision(model) and db is not None and user is not None
    last = len(windowed) - 1
    thread_files: list[dict] = []
    seen_files: set[str] = set()
    for item in windowed:
        if item.get("role") != "user":
            continue
        for file in item.get("files") or []:
            if not isinstance(file, dict):
                continue
            key = str(file.get("media_id") or file.get("filename") or "")
            if not key or key in seen_files:
                continue
            seen_files.add(key)
            thread_files.append(file)
    prepared: list[dict] = []
    for index, item in enumerate(windowed):
        files = item.get("files") or []
        full = index == last and item.get("role") == "user"
        if full:
            source_files: list[dict] = []
            own_seen: set[str] = set()
            for file in [*files, *thread_files]:
                if not isinstance(file, dict):
                    continue
                key = str(file.get("media_id") or file.get("filename") or "")
                if not key or key in own_seen:
                    continue
                own_seen.add(key)
                source_files.append(file)
            include_extracts = True
        else:
            source_files = [file for file in files if isinstance(file, dict)]
            include_extracts = False
        text = merge_attachment_text(item.get("content") or "", source_files, include_extracts=include_extracts)
        if full and vision and source_files:
            parts = vision_parts(db, user, source_files)
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
    cap = _THREAD_TRIM_TARGET if trim_cap is None else max(_THREAD_TRIM_MIN, int(trim_cap))
    return _trim_prepared_for_cap(prepared, cap)


def latest_user_files(history: list[dict]) -> list:
    for item in reversed(history or []):
        files = item.get("files") or []
        if item.get("role") == "user" and files:
            return list(files)
    return []
