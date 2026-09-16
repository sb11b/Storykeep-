from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.http_limits import redact_secrets
from app.services.demo_lock import is_locked

logger = logging.getLogger(__name__)

TOOL_NAME = "web_search"
QUERY_CHAR_CAP = 400
RESULT_CAP = 5
SNIPPET_CHAR_CAP = 280
TITLE_CHAR_CAP = 160
SEARCH_TIMEOUT_SEC = 20.0
SEARCH_CONNECT_SEC = 8.0
UI_UNAVAILABLE = "Search unavailable, retry later."
EMPTY_TOAST = "no public hits; answering from training."
EMPTY_SYSTEM = (
    "web_search returned no public hits. Answer from training. "
    "Say there were no public hits. Never say you cannot search or do not have web access."
)
LOG_NOT_CONFIGURED = "Search is not configured"
DEMO_DETAIL = "Search is not enabled on this account"
SEARCH_EXTRACT_SYSTEM = """Search the public web.
Return a JSON array of at most 5 objects with keys title, url, snippet.
Titles, URLs, and short snippets only. No HTML.
Skip uCertify, publisher paywalls, and login walls.
If there are no public hits, return []."""
SEARCH_ON_APPEND = """
You have live web_search. For current events, prices, docs, scores, UTC/date sources, or “look this up”, you MUST call web_search before answering.
Cite each source as [title](url).
If web_search fails, say the search tool failed and include the status — never that you cannot search, cannot browse, or do not have web access.
Do not scrape uCertify, publisher paywalls, or login walls. Public pages / search API only.
"""
_RETRY_STATUSES = frozenset({401, 408, 429, 503})
_TOOL_TYPES = ("live_search", "web_search")
_BLOCKED_HOST_RE = re.compile(
    r"(?:^|\.)(?:ucertify\.com|chegg\.com|coursehero\.com)$",
    re.I,
)
_LOOKUP_RE = re.compile(
    r"\b(?:look(?:ing)?(?:\s+\w+){0,3}\s+up|search(?:\s+the\s+web)?|google|"
    r"current(?:\s+\w+){0,4}|latest|today|right now|utc|score|prices?|"
    r"documentation|docs\b|what(?:'s| is|s) (?:the )?(?:nfl|date|time)|"
    r"nfl\b|stock|weather|who won|headline|news)\b",
    re.I,
)
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_SCRIPT_RE = re.compile(r"<(script|style).*?>.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>", re.S)

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": TOOL_NAME,
        "description": (
            "Search the public web. Use for current events, prices, docs, scores, "
            "UTC/date sources, or when Steve asks to look something up. "
            "Returns titles, URLs, and snippets only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Public-web search query",
                    "maxLength": QUERY_CHAR_CAP,
                },
            },
            "required": ["query"],
        },
    },
}


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class SearchOutcome:
    hits: tuple[SearchHit, ...]
    empty: bool
    toast: str | None
    fatal: bool
    status_code: int
    detail: str

    def as_payload(self) -> dict[str, object]:
        return {
            "hits": [{"title": hit.title, "url": hit.url, "snippet": hit.snippet} for hit in self.hits],
            "empty": self.empty,
            "toast": self.toast,
        }


def configured() -> bool:
    key = (settings.xai_api_key or "").strip()
    return bool(key) and key.startswith("xai-")


def owner_can_search(user: object | None) -> bool:
    return configured() and not is_locked(user)


def wants_web_search(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    return bool(_LOOKUP_RE.search(text))


def is_web_search_tool(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    kind = str(item.get("type") or "").strip()
    if kind in {"live_search", "web_search"}:
        return True
    fn = item.get("function") if isinstance(item.get("function"), dict) else {}
    name = str(fn.get("name") or item.get("name") or "").strip()
    return name == TOOL_NAME


def reject_demo(user: object) -> None:
    if is_locked(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=DEMO_DETAIL)


def clamp_query(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").strip())[:QUERY_CHAR_CAP]


def format_hits_for_model(hits: tuple[SearchHit, ...] | list[SearchHit]) -> str:
    lines = ["Live web_search results for this turn (titles, URLs, snippets only):"]
    for index, hit in enumerate(hits[:RESULT_CAP], start=1):
        snippet = hit.snippet.strip()
        tail = f" — {snippet}" if snippet else ""
        lines.append(f"{index}. [{hit.title}]({hit.url}){tail}")
    lines.append("Cite title + URL in the reply. Do not dump HTML. Skip paywalls and login walls.")
    return "\n".join(lines)


def assemble_web_search_query(fragments: list[dict] | None) -> str | None:
    buckets: dict[int, dict[str, str]] = {}
    for item in fragments or []:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index") or 0)
        except (TypeError, ValueError):
            index = 0
        slot = buckets.setdefault(index, {"name": "", "arguments": ""})
        fn = item.get("function") if isinstance(item.get("function"), dict) else {}
        name = fn.get("name") or item.get("name")
        if isinstance(name, str) and name:
            slot["name"] = name
        args = fn.get("arguments") if isinstance(fn, dict) else item.get("arguments")
        if isinstance(args, str):
            slot["arguments"] += args
    for slot in buckets.values():
        if slot.get("name") != TOOL_NAME:
            continue
        try:
            parsed = json.loads(slot.get("arguments") or "{}")
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        query = clamp_query(str(parsed.get("query") or parsed.get("q") or ""))
        if query:
            return query
    return None


def search(query: str) -> SearchOutcome:
    cleaned = clamp_query(query)
    if not cleaned:
        return SearchOutcome((), True, EMPTY_TOAST, False, 200, EMPTY_TOAST)
    if not configured():
        logger.warning(LOG_NOT_CONFIGURED)
        return SearchOutcome((), False, UI_UNAVAILABLE, True, 503, UI_UNAVAILABLE)
    last_status = 502
    last_detail = UI_UNAVAILABLE
    for attempt in range(2):
        try:
            hits, retryable, http_status, detail = _search_once(cleaned)
        except httpx.TimeoutException:
            last_status = 504
            last_detail = _fail_detail(504, "timeout")
            if attempt == 0:
                continue
            return SearchOutcome((), False, last_detail, True, last_status, last_detail)
        except httpx.HTTPError:
            last_status = 502
            last_detail = _fail_detail(502, "transport")
            if attempt == 0:
                continue
            return SearchOutcome((), False, last_detail, True, last_status, last_detail)
        if hits:
            return SearchOutcome(tuple(hits[:RESULT_CAP]), False, None, False, 200, "")
        if retryable and attempt == 0:
            last_status = http_status
            last_detail = detail
            continue
        if retryable:
            return SearchOutcome((), False, detail, True, http_status, detail)
        return SearchOutcome((), True, EMPTY_TOAST, False, 200, EMPTY_TOAST)
    return SearchOutcome((), False, last_detail, True, last_status, last_detail)


def extract_hits(body: object) -> list[SearchHit]:
    found: list[SearchHit] = []
    seen: set[str] = set()

    def add(title: str, url: str, snippet: str) -> None:
        hit = _normalize_hit(title, url, snippet)
        if hit is None or hit.url in seen:
            return
        seen.add(hit.url)
        found.append(hit)

    if not isinstance(body, dict):
        return []
    text = _output_text(body)
    for hit in _hits_from_json(text):
        add(hit.title, hit.url, hit.snippet)
    for item in body.get("output") or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "")
        action = item.get("action") if isinstance(item.get("action"), dict) else {}
        if "search" in kind or kind.endswith("_search_call"):
            url = str(action.get("url") or item.get("url") or "")
            title = str(action.get("title") or item.get("title") or "")
            snippet = str(action.get("snippet") or action.get("query") or "")
            add(title, url, snippet)
            for result in action.get("results") or item.get("results") or []:
                if isinstance(result, dict):
                    add(
                        str(result.get("title") or ""),
                        str(result.get("url") or ""),
                        str(result.get("snippet") or result.get("text") or ""),
                    )
        content = item.get("content")
        if isinstance(content, list):
            for chunk in content:
                if not isinstance(chunk, dict):
                    continue
                for annotation in chunk.get("annotations") or []:
                    if not isinstance(annotation, dict):
                        continue
                    add(
                        str(annotation.get("title") or ""),
                        str(annotation.get("url") or annotation.get("uri") or ""),
                        "",
                    )
                chunk_text = chunk.get("text")
                if isinstance(chunk_text, str):
                    for title, url in _MD_LINK_RE.findall(chunk_text):
                        add(title, url, "")
    if not found:
        for title, url in _MD_LINK_RE.findall(text):
            add(title, url, "")
    citations = body.get("citations")
    if isinstance(citations, list):
        for item in citations:
            if isinstance(item, str):
                add("", item, "")
            elif isinstance(item, dict):
                add(str(item.get("title") or ""), str(item.get("url") or ""), str(item.get("snippet") or ""))
    return found[:RESULT_CAP]


def _search_once(query: str) -> tuple[list[SearchHit], bool, int, str]:
    key = (settings.xai_api_key or "").strip()
    url = _responses_url()
    payload: dict[str, object] = {
        "model": "grok-4.6",
        "input": [
            {"role": "system", "content": SEARCH_EXTRACT_SYSTEM},
            {"role": "user", "content": query},
        ],
        "store": False,
        "max_output_tokens": 800,
        "reasoning": {"effort": "low"},
    }
    last_status = 502
    last_detail = UI_UNAVAILABLE
    timeout = httpx.Timeout(
        SEARCH_TIMEOUT_SEC,
        connect=SEARCH_CONNECT_SEC,
        read=SEARCH_TIMEOUT_SEC,
        write=15.0,
        pool=10.0,
    )
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    for tool_type in _TOOL_TYPES:
        payload["tools"] = [{"type": tool_type}]
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=payload, headers=headers)
        last_status = response.status_code
        if response.status_code >= 400:
            last_detail = _detail_from_http(response.status_code, response.text)
            if response.status_code in {400, 410, 422}:
                continue
            retryable = response.status_code in _RETRY_STATUSES or _quota_in(last_detail)
            return [], retryable, response.status_code, last_detail
        try:
            body = response.json()
        except json.JSONDecodeError:
            last_detail = _fail_detail(502, "non-JSON")
            return [], True, 502, last_detail
        hits = extract_hits(body if isinstance(body, dict) else {})
        if hits:
            return hits, False, 200, ""
        last_detail = EMPTY_TOAST
        last_status = 200
        continue
    retryable = last_status in _RETRY_STATUSES
    return [], retryable, last_status, last_detail


def _responses_url() -> str:
    url = (settings.xai_chat_url or "https://api.x.ai/v1/chat/completions").strip()
    if url.endswith("chat/completions"):
        return url[: -len("chat/completions")] + "responses"
    return "https://api.x.ai/v1/responses"


def _plain(text: str) -> str:
    cleaned = _SCRIPT_RE.sub(" ", text or "")
    cleaned = _TAG_RE.sub(" ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _normalize_hit(title: str, url: str, snippet: str) -> SearchHit | None:
    href = (url or "").strip()
    if not href.startswith("http://") and not href.startswith("https://"):
        return None
    host = re.sub(r"^https?://", "", href, flags=re.I).split("/", 1)[0].split(":", 1)[0].lower()
    if host.startswith("www."):
        host = host[4:]
    if _BLOCKED_HOST_RE.search(host):
        return None
    if "/login" in href.lower() or "/signin" in href.lower():
        return None
    label = _plain(title)[:TITLE_CHAR_CAP] or host
    blurb = _plain(snippet)[:SNIPPET_CHAR_CAP]
    return SearchHit(label, href, blurb)


def _hits_from_json(text: str) -> list[SearchHit]:
    blob = (text or "").strip()
    if "```" in blob:
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", blob, re.I)
        if fence:
            blob = fence.group(1).strip()
    start = blob.find("[")
    end = blob.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        parsed = json.loads(blob[start : end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    hits: list[SearchHit] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        hit = _normalize_hit(
            str(item.get("title") or ""),
            str(item.get("url") or item.get("href") or ""),
            str(item.get("snippet") or item.get("text") or ""),
        )
        if hit:
            hits.append(hit)
    return hits


def _output_text(body: dict) -> str:
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


def _quota_in(detail: str) -> bool:
    lower = (detail or "").lower()
    return "quota" in lower or "rate limit" in lower or "too many requests" in lower


def _fail_detail(http_status: int, reason: str) -> str:
    label = redact_secrets((reason or "error").strip()) or "error"
    return f"Search failed (HTTP {http_status}): {label}"


def _detail_from_http(http_status: int, raw: str) -> str:
    text = redact_secrets((raw or "").strip())[:300]
    reason = "error"
    if http_status == 401:
        reason = "auth"
    elif http_status == 429 or _quota_in(text):
        reason = "quota"
    elif http_status in {408, 504}:
        reason = "timeout"
    elif text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            err = parsed.get("error")
            if isinstance(err, dict):
                message = err.get("message") or err.get("code")
                if isinstance(message, str) and message.strip():
                    reason = message.strip()[:80]
            elif isinstance(parsed.get("message"), str):
                reason = str(parsed.get("message")).strip()[:80]
        if reason == "error" and _quota_in(text):
            reason = "quota"
    return _fail_detail(http_status, reason)
