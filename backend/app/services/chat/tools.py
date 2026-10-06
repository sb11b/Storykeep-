from __future__ import annotations

import json
import re
import logging
from uuid import UUID

import httpx
from fastapi import HTTPException

from app.http_limits import log_model_call

from ._shared import (
    MAX_TOKENS_CAP,
    _content_text,
    resolved_max_output_tokens,
)
from ._http import (
    CHAT_CONNECT_TIMEOUT_SEC,
    _auth_headers,
    _canopy_enabled,
    _chat_timeout,
    _transport_error_detail,
    _xai_key,
    _xai_responses_url,
    chat_url,
    map_xai_http_error,
    parse_xai_error_body,
    require_key,
)
from .attachments import messages_char_count
from .model_routing import (
    DEFAULT_REASONING_EFFORT,
    attach_reasoning_effort,
    clamp_reasoning_effort,
    default_full_model,
    model_uses_reasoning,
    rewrite_xai_model,
)
from .streaming import _strip_canopy_tool_markup

logger = logging.getLogger(__name__)


# Chat Completions rejects code_interpreter (422). Send may only attach function / live_search.
COMPLETIONS_ALLOWED_TOOL_TYPES = frozenset({"function", "live_search"})
RESPONSES_SEARCH_TOOL_TYPES = ("live_search", "web_search")
RESPONSES_CODE_TOOL_TYPES = ("code_execution",)


def filter_completions_tools(tools: list[dict] | None) -> list[dict] | None:
    """Drop code_interpreter and any type Completions does not allow."""
    kept: list[dict] = []
    for item in tools or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").strip()
        if kind in COMPLETIONS_ALLOWED_TOOL_TYPES:
            kept.append(item)
    return kept or None


def wants_responses_search(tools: list[dict] | None) -> bool:
    for item in tools or []:
        if isinstance(item, dict) and str(item.get("type") or "").strip() in {"web_search", "live_search"}:
            return True
    return False


def build_chat_completions_payload(
    *,
    messages: list[dict],
    model: str,
    reasoning_effort: str,
    max_tokens: int,
    stream: bool,
    temperature: float,
    tools: list[dict] | None = None,
) -> dict[str, object]:
    resolved_model = rewrite_xai_model(model)
    effort = clamp_reasoning_effort(resolved_model, reasoning_effort)
    capped = min(MAX_TOKENS_CAP, max(64, int(max_tokens)))
    payload: dict[str, object] = {
        "model": resolved_model,
        "messages": messages,
        "stream": stream,
        "max_tokens": capped,
        "max_completion_tokens": capped,
        "temperature": temperature,
    }
    allowed = filter_completions_tools(tools)
    if allowed:
        payload["tools"] = allowed
    dumped = json.dumps(payload)
    if "code_interpreter" in dumped:
        payload.pop("tools", None)
    return attach_reasoning_effort(payload, resolved_model, effort)


def parse_responses_text(body: dict) -> str:
    direct = body.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    parts: list[str] = []
    for item in body.get("output") or []:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, list):
            for chunk in content:
                if not isinstance(chunk, dict):
                    continue
                if chunk.get("type") in {"output_text", "text"}:
                    text = chunk.get("text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
        elif item.get("type") in {"output_text", "text"}:
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n".join(parts).strip()


def responses_used_search(body: dict) -> bool:
    for item in body.get("output") or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "")
        if "web_search" in kind or "live_search" in kind or kind.endswith("_search_call"):
            return True
    return False


_CANT_SEARCH = re.compile(
    r"i can['’]?t (search|browse)|cannot search|can not search|don't have (web |internet )?access|do not have web",
    re.I,
)


def complete_with_server_tools(
    messages: list[dict],
    *,
    tool_types: tuple[str, ...],
    model: str | None = None,
    reasoning_effort: str | None = None,
    max_tokens: int = 1200,
    timeout_sec: float = 90.0,
    fail_detail: str = "search failed",
    require_search: bool = False,
    log_chat_id: UUID | str | None = None,
    log_slice_id: str | None = None,
) -> dict[str, str]:
    """POST /v1/responses with a server tool. Never send code_interpreter."""
    kinds = tuple(kind for kind in tool_types if kind and kind != "code_interpreter")
    if not kinds:
        raise HTTPException(status_code=502, detail=fail_detail)
    key = _xai_key()
    resolved_model = rewrite_xai_model(model or default_full_model())
    effort = clamp_reasoning_effort(resolved_model, reasoning_effort or DEFAULT_REASONING_EFFORT)
    payload: dict[str, object] = {
        "model": resolved_model,
        "input": messages,
        "store": False,
        "max_output_tokens": min(MAX_TOKENS_CAP, max(64, int(max_tokens))),
    }
    if model_uses_reasoning(resolved_model):
        payload["reasoning"] = {"effort": effort}
    log_model_call(
        chat_id=log_chat_id,
        slice_id=log_slice_id,
        n_chars=messages_char_count(messages),
    )
    last_detail = fail_detail
    for tool_type in kinds:
        payload["tools"] = [{"type": tool_type}]
        try:
            with httpx.Client(
                timeout=httpx.Timeout(
                    timeout_sec,
                    connect=CHAT_CONNECT_TIMEOUT_SEC,
                    read=timeout_sec,
                    write=15.0,
                    pool=10.0,
                )
            ) as client:
                response = client.post(_xai_responses_url(), json=payload, headers=_auth_headers(key))
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=_transport_error_detail(exc)) from exc
        if response.status_code >= 400:
            last_detail = parse_xai_error_body(response.text, response.status_code)
            if response.status_code in {400, 410, 422}:
                continue
            raise map_xai_http_error(response.status_code, last_detail, resolved_model)
        try:
            body = response.json()
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="xAI returned a non-JSON reply.") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=502, detail=fail_detail)
        text = parse_responses_text(body)
        if not text:
            raise HTTPException(status_code=502, detail=fail_detail)
        if require_search and _CANT_SEARCH.search(text) and not responses_used_search(body):
            raise HTTPException(status_code=502, detail=fail_detail)
        return {"text": text, "model": resolved_model, "reasoning": effort}
    raise HTTPException(status_code=502, detail=last_detail or fail_detail)


def complete_with_web_search(
    messages: list[dict],
    *,
    model: str | None = None,
    reasoning_effort: str | None = None,
    max_tokens: int = 1200,
    timeout_sec: float = 90.0,
    log_chat_id: UUID | str | None = None,
    log_slice_id: str | None = None,
) -> dict[str, str]:
    """Junior job search via Responses live_search. Completions 422s code_interpreter."""
    return complete_with_server_tools(
        messages,
        tool_types=RESPONSES_SEARCH_TOOL_TYPES,
        model=model,
        reasoning_effort=reasoning_effort,
        max_tokens=max_tokens,
        timeout_sec=timeout_sec,
        fail_detail="search failed",
        require_search=True,
        log_chat_id=log_chat_id,
        log_slice_id=log_slice_id,
    )


def complete_with_code_execution(
    messages: list[dict],
    *,
    model: str | None = None,
    reasoning_effort: str | None = None,
    max_tokens: int = 700,
    timeout_sec: float = 60.0,
) -> dict[str, str]:
    """In-thread Run uses Responses code_execution — never code_interpreter."""
    return complete_with_server_tools(
        messages,
        tool_types=RESPONSES_CODE_TOOL_TYPES,
        model=model,
        reasoning_effort=reasoning_effort,
        max_tokens=max_tokens,
        timeout_sec=timeout_sec,
        fail_detail="Could not run that snippet.",
        require_search=False,
    )


complete_with_code_interpreter = complete_with_code_execution


def complete_once(
    messages: list[dict],
    *,
    model: str | None = None,
    reasoning_effort: str | None = None,
    max_tokens: int = 1200,
    timeout_sec: float = 45.0,
    tools: list[dict] | None = None,
    log_chat_id: UUID | str | None = None,
    log_slice_id: str | None = None,
) -> dict[str, str]:
    """One-shot chat for Junior jobs. Never POST code_interpreter on Completions."""
    if wants_responses_search(tools):
        return complete_with_web_search(
            messages,
            model=model,
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
            timeout_sec=timeout_sec,
            log_chat_id=log_chat_id,
            log_slice_id=log_slice_id,
        )
    key = require_key()
    resolved_model = rewrite_xai_model(model or default_full_model())
    effort = clamp_reasoning_effort(resolved_model, reasoning_effort or DEFAULT_REASONING_EFFORT)
    payload = build_chat_completions_payload(
        messages=messages,
        model=resolved_model,
        reasoning_effort=effort,
        max_tokens=max_tokens,
        stream=False,
        temperature=0.4,
        tools=tools,
    )
    log_model_call(
        chat_id=log_chat_id,
        slice_id=log_slice_id,
        n_chars=messages_char_count(messages),
    )
    try:
        with httpx.Client(
            timeout=httpx.Timeout(
                timeout_sec,
                connect=CHAT_CONNECT_TIMEOUT_SEC,
                read=timeout_sec,
                write=15.0,
                pool=10.0,
            )
        ) as client:
            response = client.post(chat_url(), json=payload, headers=_auth_headers(key))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=_transport_error_detail(exc)) from exc
    if response.status_code >= 400:
        detail = parse_xai_error_body(response.text, response.status_code)
        raise map_xai_http_error(response.status_code, detail, resolved_model)
    try:
        body = response.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="xAI returned a non-JSON reply.") from exc
    choices = body.get("choices") or []
    message = (choices[0].get("message") or {}) if choices else {}
    text = _content_text(message.get("content") if isinstance(message, dict) else "").strip()
    if not text:
        raise HTTPException(status_code=502, detail="Grok returned an empty reply.")
    if _canopy_enabled():
        text = _strip_canopy_tool_markup(text)
    return {"text": text, "model": resolved_model, "reasoning": effort}
