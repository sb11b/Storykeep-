from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.http_limits import log_model_call

from ._shared import (
    CHAT_CONNECT_TIMEOUT_SEC,
    CHAT_FIRST_BYTE_TIMEOUT_HEAVY_SEC,
    CHAT_FIRST_BYTE_TIMEOUT_MAX_SEC,
    CHAT_FIRST_BYTE_TIMEOUT_SEC,
    CHAT_HEALTH_TIMEOUT_SEC,
    CHAT_IDLE_AFTER_TOKEN_MAX_SEC,
    CHAT_IDLE_AFTER_TOKEN_MIN_SEC,
    CHAT_STREAM_TIMEOUT_SEC,
    CURRENT_CHAT_MODEL,
    DEFAULT_REASONING_EFFORT,
    MODEL_AUTO,
    REASONING_AUTO,
    SEND_THREAD_TOO_LARGE,
    SSE_PADDING,
    STREAM_HEARTBEAT,
    XAI_EMPTY_DETAIL,
    XAI_SILENT_DETAIL,
    _content_text,
    chat_idle_after_token_sec,
    chat_idle_timeout_detail,
    resolved_max_output_tokens,
)
from ._http import (
    XAI_MODELS_CACHE_SEC,
    _auth_headers,
    _canopy_enabled,
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
from .model_routing import (
    MODEL_AUTO,
    REASONING_AUTO,
    attach_reasoning_effort,
    clamp_reasoning_effort,
    default_full_model,
    model_uses_reasoning,
    normalize_model_choice,
    posted_spend_label,
    rewrite_xai_model,
    should_attach_chat_tools,
)

logger = logging.getLogger(__name__)


def is_recoverable_empty_reply(status_code: int, detail: str) -> bool:
    """Empty/silent streams should surface fallback text, not a bare error bubble."""
    if status_code not in {502, 504}:
        return False
    cleaned = (detail or "").strip().lower()
    if status_code == 504 and not cleaned:
        return True
    return "xai silent" in cleaned or "returned no text" in cleaned


def chat_error_message(status2: int, detail: str) -> str:
    cleaned = (detail or "Unknown error.").strip()
    return f"Chat failed (HTTP {status2}): {cleaned}"


def stream_error_event(status: int, detail: str, *, partial: bool = False) -> dict[str, object]:
    from app.http_limits import redact_secrets

    message = redact_secrets(detail.strip() or "Unknown error.")
    return {
        "error": chat_error_message(status, message),
        "message": message,
        "status": status,
        "detail": message,
        "partial": partial,
    }


def encode_sse(payload: dict[str, object] | str) -> bytes:
    """One SSE event as bytes so ASGI can flush it immediately."""
    if isinstance(payload, str):
        return f"data: {payload}\n\n".encode("utf-8")
    return ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")


async def _anext_or_none(lines: AsyncIterator[str]) -> str | None:
    try:
        return await anext(lines)
    except StopAsyncIteration:
        return None


def http_exception_detail(exc: HTTPException) -> tuple[int, str]:
    status_code = int(exc.status_code or 502)
    detail = exc.detail
    if isinstance(detail, str) and detail.strip():
        return status_code, detail
    if isinstance(detail, list):
        parts: list[str] = []
        for item in detail:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, dict):
                msg = item.get("msg") or item.get("message")
                if isinstance(msg, str) and msg.strip():
                    parts.append(msg.strip())
        if parts:
            return status_code, "; ".join(parts)
    return status_code, "Request failed."


async def pace_stream(source: AsyncIterator[str], interval: float = 8.0) -> AsyncIterator[str | object]:
    """Yield source items, and STREAM_HEARTBEAT whenever the source is quiet.

    Proxies and the browser drop chat streams that go ~60s with no bytes. xAI
    often sits that long before the first token, which surfaced as "No reply".
    """
    end = object()
    queue: asyncio.Queue[object] = asyncio.Queue()

    async def pump() -> None:
        try:
            async for piece in source:
                await queue.put(piece)
        except Exception as exc:
            await queue.put(exc)
        finally:
            await queue.put(end)

    task = asyncio.create_task(pump())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=interval)
            except asyncio.TimeoutError:
                yield STREAM_HEARTBEAT
                continue
            if item is end:
                return
            if isinstance(item, Exception):
                raise item
            yield item
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


def _parse_sse_payload(raw: str) -> tuple[str, bool, list[dict]]:
    """Return (user-visible text, activity, tool_call fragments)."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return "", False, []
    choices = parsed.get("choices") or []
    if not choices:
        return "", False, []
    choice = choices[0] if isinstance(choices[0], dict) else {}
    delta = choice.get("delta") or {}
    message = choice.get("message") or {}
    visible = (
        _content_text(delta.get("content"))
        or _content_text(delta.get("text"))
        or _content_text(message.get("content"))
        or _content_text(message.get("text"))
        or _content_text(choice.get("text"))
    )
    reasoning = delta.get("reasoning_content") or message.get("reasoning_content")
    tool_calls = delta.get("tool_calls") or []
    bits = [item for item in tool_calls if isinstance(item, dict)]
    if not bits:
        extra = message.get("tool_calls") or []
        bits = [item for item in extra if isinstance(item, dict)]
    active = bool(visible) or (isinstance(reasoning, str) and bool(reasoning)) or bool(bits)
    return visible, active, bits


def _parse_sse_chunk(raw: str) -> tuple[str, bool]:
    text, active, _ = _parse_sse_payload(raw)
    return text, active


def _delta_text(raw: str) -> str:
    text, _ = _parse_sse_chunk(raw)
    return text


def _strip_canopy_tool_markup(text: str) -> str:
    stripped = text or ""
    stripped = re.sub(r" uphill.*? downhill", "", stripped, flags=re.DOTALL)
    stripped = re.sub(r" downhill", "", stripped)
    stripped = re.sub(r"<\|thinking_begin\|>.*?<\|thinking_end\|>", "", stripped, flags=re.DOTALL)
    stripped = re.sub(r"<\|tool_calls_section_begin\|>.*?<\|tool_calls_section_end\|>", "", stripped, flags=re.DOTALL)
    stripped = re.sub(r"<\|tool_call_begin\|>.*?<\|tool_call_end\|>", "", stripped, flags=re.DOTALL)
    stripped = re.sub(r"<\|tool_calls_section_begin\|>.*", "", stripped, flags=re.DOTALL)
    stripped = re.sub(r"<\|tool_call_begin\|>.*", "", stripped, flags=re.DOTALL)
    for opener in (" uphill", "<|thinking_begin|>"):
        cut = stripped.find(opener)
        if cut != -1:
            stripped = stripped[:cut]
    return stripped.strip()


def ping_xai() -> dict[str, object]:
    """Streaming 1-token probe for GET /chat/health. Stops at first visible token."""
    import app.services.chat as _pkg
    key = _pkg.require_key()
    model = rewrite_xai_model(default_full_model())
    reasoning = DEFAULT_REASONING_EFFORT
    payload = attach_reasoning_effort(
        {
            "model": model,
            "messages": [{"role": "user", "content": "ping"}],
            "stream": True,
            "max_tokens": 8,
            "temperature": 0,
        },
        model,
        reasoning,
    )
    started = time.perf_counter()
    ping_timeout = httpx.Timeout(
        timeout=CHAT_FIRST_BYTE_TIMEOUT_SEC,
        connect=CHAT_CONNECT_TIMEOUT_SEC,
        read=CHAT_FIRST_BYTE_TIMEOUT_SEC,
        write=8.0,
        pool=5.0,
    )
    try:
        with _pkg.httpx.Client(timeout=ping_timeout) as client:
            with client.stream(
                "POST",
                chat_url(),
                json=payload,
                headers={**_auth_headers(key), "Accept": "text/event-stream"},
            ) as response:
                xai_status = response.status_code
                if xai_status >= 400:
                    body = response.read().decode("utf-8", errors="replace")
                    ttft_ms = int((time.perf_counter() - started) * 1000)
                    detail = parse_xai_error_body(body, xai_status)
                    if xai_status == 401:
                        detail = "xAI auth failed"
                    _xai_ttft_log(
                        ok=False,
                        ttft_ms=ttft_ms,
                        model=model,
                        reasoning=reasoning,
                        xai_status=xai_status,
                    )
                    return {
                        "ok": False,
                        "model": model,
                        "reasoning": reasoning,
                        "ttft_ms": ttft_ms,
                        "xai_status": xai_status,
                        "message": detail,
                    }
                for line in response.iter_lines():
                    if time.perf_counter() - started >= CHAT_FIRST_BYTE_TIMEOUT_SEC:
                        break
                    if not line:
                        continue
                    data = line[5:].strip() if line.startswith("data:") else line.strip()
                    if data == "[DONE]":
                        break
                    text, active = _parse_sse_chunk(data)
                    if text or active:
                        ttft_ms = int((time.perf_counter() - started) * 1000)
                        _xai_ttft_log(
                            ok=True,
                            ttft_ms=ttft_ms,
                            model=model,
                            reasoning=reasoning,
                            xai_status=xai_status,
                        )
                        return {
                            "ok": True,
                            "model": model,
                            "reasoning": reasoning,
                            "ttft_ms": ttft_ms,
                            "xai_status": xai_status,
                        }
                ttft_ms = int((time.perf_counter() - started) * 1000)
                _xai_ttft_log(
                    ok=False,
                    ttft_ms=ttft_ms,
                    model=model,
                    reasoning=reasoning,
                    xai_status=xai_status,
                )
                return {
                    "ok": False,
                    "model": model,
                    "reasoning": reasoning,
                    "ttft_ms": ttft_ms,
                    "xai_status": xai_status,
                    "message": XAI_SILENT_DETAIL,
                }
    except httpx.HTTPError as exc:
        ttft_ms = int((time.perf_counter() - started) * 1000)
        xai_status: int | str | None = "timeout" if isinstance(
            exc, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException)
        ) else None
        _xai_ttft_log(
            ok=False,
            ttft_ms=ttft_ms,
            model=model,
            reasoning=reasoning,
            xai_status=xai_status,
        )
        return {
            "ok": False,
            "model": model,
            "reasoning": reasoning,
            "ttft_ms": ttft_ms,
            "xai_status": xai_status,
            "message": XAI_SILENT_DETAIL if xai_status == "timeout" else _transport_error_detail(exc),
        }


async def stream_completion(
    history: list[dict],
    excerpt: str | None,
    *,
    include_article: bool,
    recap_question: bool = False,
    model: str,
    model_choice: str = MODEL_AUTO,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
    user_id: UUID | None = None,
    has_attachments: bool = False,
    include_note: bool = False,
    note_excerpt: str | None = None,
    extra_system: str | None = None,
    working_excerpt: str | None = None,
    cancelled: asyncio.Event | None = None,
    tools: list[dict] | None = None,
    tool_calls_out: list[dict] | None = None,
    log_chat_id: UUID | str | None = None,
    log_slice_id: str | None = None,
    log_message_id: UUID | str | None = None,
    messages_override: list[dict] | None = None,
    first_byte_timeout: float | None = None,
) -> AsyncIterator[str]:
    from .attachments import build_xai_messages, messages_char_count
    from .tools import build_chat_completions_payload
    import app.services.chat as _pkg
    key = _pkg.require_key()
    model = rewrite_xai_model(model)
    reasoning_effort = clamp_reasoning_effort(model, reasoning_effort)
    max_tokens = resolved_max_output_tokens()
    idle_after_token_sec = chat_idle_after_token_sec(max_tokens)
    last_user = ""
    for item in reversed(history or []):
        if (item.get("role") or "") == "user":
            content = item.get("content")
            last_user = content if isinstance(content, str) else ""
            break
    if _canopy_enabled():
        # Canopy does not support web_search / code_execution; strip those tools.
        attach_tools = None
    elif should_attach_chat_tools(last_user):
        attach_tools = tools
    else:
        from app.services.chat_index import is_chat_index_tool
        from app.services.cursor_agent_tool import is_cursor_tool
        from app.services.github_tool import is_github_tool
        from app.services.railway_tool import is_railway_tool
        from app.services.web_search import is_web_search_tool

        attach_tools = [
            item
            for item in (tools or [])
            if is_web_search_tool(item)
            or is_chat_index_tool(item)
            or is_railway_tool(item)
            or is_github_tool(item)
            or is_cursor_tool(item)
        ] or None
    if messages_override is not None:
        xai_messages = messages_override
    else:
        from app.services import junior_model

        xai_messages = build_xai_messages(
            history,
            excerpt,
            include_article=include_article,
            recap_question=recap_question,
            has_attachments=has_attachments,
            include_note=include_note,
            note_excerpt=note_excerpt,
            working_excerpt=working_excerpt,
            extra_system=extra_system,
            thread_limit=junior_model.JUNIOR_THREAD_WINDOW,
        )
    payload = build_chat_completions_payload(
        messages=xai_messages,
        model=model,
        reasoning_effort=reasoning_effort,
        max_tokens=max_tokens,
        stream=True,
        temperature=0.6,
        tools=attach_tools,
    )
    log_model_call(
        user_id=user_id,
        chat_id=log_chat_id,
        message_id=log_message_id,
        slice_id=log_slice_id,
        n_chars=messages_char_count(xai_messages),
        status="stream",
    )
    started = time.perf_counter()
    first_token_at: float | None = None
    xai_status: int | str | None = None
    canopy_buf: str = ""  # accumulate across SSE lines when inside Kimi markers
    canopy_visible_sent = False  # did any user-visible text leave this stream?
    fb_timeout = (
        float(first_byte_timeout)
        if first_byte_timeout is not None
        else float(CHAT_FIRST_BYTE_TIMEOUT_SEC)
    )
    try:
        async with _pkg.httpx.AsyncClient(timeout=_chat_timeout(streaming=True)) as client:
            async with client.stream(
                "POST",
                chat_url(),
                json=payload,
                headers={**_auth_headers(key), "Accept": "text/event-stream"},
            ) as response:
                xai_status = response.status_code
                if xai_status >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    detail = parse_xai_error_body(body, xai_status)
                    if tools and xai_status in {400, 422}:
                        async for piece in stream_completion(
                            history,
                            excerpt,
                            include_article=include_article,
                            recap_question=recap_question,
                            model=model,
                            model_choice=model_choice,
                            reasoning_effort=reasoning_effort,
                            user_id=user_id,
                            has_attachments=has_attachments,
                            include_note=include_note,
                            note_excerpt=note_excerpt,
                            extra_system=extra_system,
                            working_excerpt=working_excerpt,
                            cancelled=cancelled,
                            tools=None,
                            tool_calls_out=tool_calls_out,
                            log_chat_id=log_chat_id,
                            log_slice_id=log_slice_id,
                            log_message_id=log_message_id,
                            messages_override=messages_override,
                            first_byte_timeout=fb_timeout,
                        ):
                            yield piece
                        return
                    _xai_ttft_log(
                        ok=False,
                        ttft_ms=int((time.perf_counter() - started) * 1000),
                        model=model,
                        reasoning=reasoning_effort,
                        xai_status=xai_status,
                    )
                    raise map_xai_http_error(xai_status, detail, model)
                # Headers received — leave "working" for thinking before the first token.
                yield ""
                lines = response.aiter_lines()
                while True:
                    if cancelled is not None and cancelled.is_set():
                        return
                    elapsed = time.perf_counter() - started
                    if first_token_at is None:
                        wait = fb_timeout - elapsed
                        if wait <= 0:
                            _xai_ttft_log(
                                ok=False,
                                ttft_ms=int(elapsed * 1000),
                                model=model,
                                reasoning=reasoning_effort,
                                xai_status=xai_status,
                            )
                            raise HTTPException(status_code=504, detail=XAI_SILENT_DETAIL)
                    else:
                        wait = idle_after_token_sec
                    line: str | None = None
                    try:
                        # One wait_for for the whole window. Sliced 0.15s waits cancel
                        # httpx aiter_lines and drop tokens that already arrived.
                        line = await asyncio.wait_for(_anext_or_none(lines), timeout=wait)
                    except asyncio.TimeoutError as exc:
                        if first_token_at is None:
                            _xai_ttft_log(
                                ok=False,
                                ttft_ms=int((time.perf_counter() - started) * 1000),
                                model=model,
                                reasoning=reasoning_effort,
                                xai_status=xai_status,
                            )
                            raise HTTPException(status_code=504, detail=XAI_SILENT_DETAIL) from exc
                        raise HTTPException(
                            status_code=504,
                            detail=chat_idle_timeout_detail(max_tokens),
                        ) from exc
                    if cancelled is not None and cancelled.is_set():
                        return
                    if line is None:
                        break
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data = line[5:].strip()
                    else:
                        data = line.strip()
                    if data == "[DONE]":
                        break
                    text, active, tool_bits = _parse_sse_payload(data)
                    if tool_bits and tool_calls_out is not None:
                        tool_calls_out.extend(tool_bits)
                        active = True
                    if not active and not text:
                        continue
                    if first_token_at is None:
                        first_token_at = time.perf_counter()
                        _xai_ttft_log(
                            ok=True,
                            ttft_ms=int((first_token_at - started) * 1000),
                            model=model,
                            reasoning=reasoning_effort,
                            xai_status=xai_status,
                        )
                        if not text:
                            # Reasoning/keepalive counts as first token so SSE can start.
                            yield ""
                            continue
                    if text:
                        if _canopy_enabled():
                            canopy_buf += text
                            # while there is visible text to yield before any open marker
                            while True:
                                # find the earliest unclosed or closed marker start
                                earliest = None
                                for pat in ("</think>", "<think>", "<|thinking_begin|>", "<|tool_call_begin|>", "<|tool_calls_section_begin|>"):
                                    idx = canopy_buf.find(pat)
                                    if idx != -1:
                                        if earliest is None or idx < earliest[0]:
                                            earliest = (idx, pat)
                                if earliest is None:
                                    # no markers at all
                                    if canopy_buf:
                                        yield canopy_buf
                                        canopy_visible_sent = True
                                        canopy_buf = ""
                                    break
                                pos, pat = earliest
                                if pos > 0:
                                    yield canopy_buf[:pos]
                                    canopy_visible_sent = True
                                    canopy_buf = canopy_buf[pos:]
                                # now starts with a marker; strip complete or unclosed blocks
                                end_pats = {
                                    "</think>": "", "<think>": "</think>", "<|thinking_begin|>": "<|thinking_end|>",
                                    "<|tool_call_begin|>": "<|tool_call_end|>",
                                    "<|tool_calls_section_begin|>": "<|tool_calls_section_end|>",
                                }
                                end_pat = end_pats[pat]
                                if end_pat == "":
                                    canopy_buf = canopy_buf[len(pat):]
                                    continue
                                end_pos = canopy_buf.find(end_pat, len(pat))
                                if end_pos != -1:
                                    canopy_buf = canopy_buf[end_pos + len(end_pat):]
                                else:
                                    # still open; hold everything
                                    break
                            continue
                        yield text
                if canopy_buf:
                    # The stream ended inside an unclosed hidden block, so the
                    # buffer holds only marker-prefixed hidden text — never show
                    # it (that would leak the model's reasoning). If no visible
                    # text ever left this stream, surface the recoverable
                    # empty-reply path instead of a silent blank turn.
                    canopy_buf = ""
                    if not canopy_visible_sent:
                        raise HTTPException(status_code=502, detail=XAI_EMPTY_DETAIL)
                if first_token_at is None:
                    _xai_ttft_log(
                        ok=False,
                        ttft_ms=int((time.perf_counter() - started) * 1000),
                        model=model,
                        reasoning=reasoning_effort,
                        xai_status=xai_status,
                    )
                    raise HTTPException(status_code=504, detail=XAI_SILENT_DETAIL)
    except HTTPException:
        raise
    except asyncio.CancelledError:
        raise
    except httpx.HTTPError as exc:
        if first_token_at is None:
            if isinstance(exc, (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.TimeoutException)):
                xai_status = "timeout"
            _xai_ttft_log(
                ok=False,
                ttft_ms=int((time.perf_counter() - started) * 1000),
                model=model,
                reasoning=reasoning_effort,
                xai_status=xai_status,
            )
            raise HTTPException(status_code=504, detail=XAI_SILENT_DETAIL) from exc
        raise HTTPException(
            status_code=504,
            detail=chat_idle_timeout_detail(max_tokens),
        ) from exc
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        if first_token_at is None:
            _xai_ttft_log(
                ok=False,
                ttft_ms=int((time.perf_counter() - started) * 1000),
                model=model,
                reasoning=reasoning_effort,
                xai_status=xai_status,
            )
            raise HTTPException(status_code=504, detail=XAI_SILENT_DETAIL) from exc
        raise HTTPException(
            status_code=504,
            detail=chat_idle_timeout_detail(max_tokens),
        ) from exc
