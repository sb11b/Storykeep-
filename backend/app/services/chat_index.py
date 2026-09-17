from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import User
from app.services import grok_conversations as grok_store
from app.services.demo_lock import is_locked

LIST_NAME = "list_chats"
READ_NAME = "read_chat"
INDEX_CAP = 40
SUMMARY_CHAR = 180
READ_MESSAGE_CAP = 8
READ_CHAR_CAP = 8_000
QUERY_CHAR_CAP = 80

CHATS_ON_APPEND = """
You can see Steve's other Junior chats with list_chats (index) and read_chat (one thread slice).
- Do not claim you have read all chats unless an index or a slice is attached this turn.
- If he says “all chats” or “catch me up”: use the attached index only. Ask which id to open next for detail.
- If he says “read this chat”: use only that attached slice. Prefer id, date, title, or topic over dumping history.
- If a slice is truncated, say so, list what you have, ask which slice next, and summarize instead of pasting everything.
- Never invent messages, calendar events, or mail. Use only attached lists and this thread.
- Keep answers short. Never append an Add-to-notes footer.
"""

NEED_ID_SYSTEM = (
    "Steve asked to read a chat but did not give a conversation id. "
    "Use the index (list_chats) and ask which id to open. Do not invent a thread."
)

INDEX_HEADER = "Junior chat index (date, title, summary, id, note id). Not full history. Cap 40."

_INDEX_RE = re.compile(
    r"\ball chats\b|"
    r"\bcatch me up\b|"
    r"\bchat index\b|"
    r"\b(other|previous|past|older)\s+chats\b|"
    r"\blist(?:\s+my|\s+the)?\s+chats\b|"
    r"\bacross chats\b",
    re.I,
)
_READ_RE = re.compile(
    r"\bread this chat\b|"
    r"\bopen (?:this |that |the )?chat\b|"
    r"\bthat thread\b|"
    r"\bread (?:that |the )?thread\b|"
    r"\bopen thread\b",
    re.I,
)
_UUID_RE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.I,
)

LIST_CHATS_TOOL = {
    "type": "function",
    "function": {
        "name": LIST_NAME,
        "description": (
            "Build Steve's Junior chat index: date, title, 1–2 sentence summary from stored "
            "messages, conversation id, saved note id. Not full history. Use before opening a thread."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Optional title/topic filter"},
                "from_date": {"type": "string", "description": "Optional YYYY-MM-DD inclusive"},
                "to_date": {"type": "string", "description": "Optional YYYY-MM-DD inclusive"},
            },
        },
    },
}

READ_CHAT_TOOL = {
    "type": "function",
    "function": {
        "name": READ_NAME,
        "description": (
            "Open one Junior chat by id. Returns a slice of messages, not the whole thread. "
            "Pass offset to get the next slice."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string", "description": "Chat UUID from the index"},
                "offset": {"type": "integer", "description": "Message offset for the next slice", "minimum": 0},
            },
            "required": ["conversation_id"],
        },
    },
}

TOOLS = [LIST_CHATS_TOOL, READ_CHAT_TOOL]


def can_use(user: object | None) -> bool:
    return user is not None and not is_locked(user)


def wants_index(message: str) -> bool:
    return bool(_INDEX_RE.search(message or ""))


def wants_read(message: str) -> bool:
    return bool(_READ_RE.search(message or ""))


def extract_conversation_id(message: str) -> UUID | None:
    match = _UUID_RE.search(message or "")
    if not match:
        return None
    try:
        return UUID(match.group(0))
    except ValueError:
        return None


def is_chat_index_tool(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    fn = item.get("function") if isinstance(item.get("function"), dict) else {}
    name = str(fn.get("name") or item.get("name") or "").strip()
    return name in {LIST_NAME, READ_NAME}


def clip(text: str, limit: int = SUMMARY_CHAR) -> str:
    one = " ".join((text or "").split())
    if len(one) <= limit:
        return one
    return one[: limit - 1].rstrip() + "…"


def _day(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).date().isoformat()


def _parse_day(raw: str | None) -> datetime | None:
    text = (raw or "").strip()[:10]
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def chats_for(db: Session, user: User) -> list[dict[str, Any]]:
    if not grok_store.should_persist(user):
        return []
    return build_index(db, user)


def build_index(
    db: Session,
    user: User,
    *,
    query: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    exclude_id: UUID | None = None,
    limit: int = INDEX_CAP,
) -> list[dict[str, Any]]:
    rows = grok_store.list_conversations(db, user)
    needle = clip(query or "", QUERY_CHAR_CAP).lower()
    start = _parse_day(from_date)
    end = _parse_day(to_date)
    out: list[dict[str, Any]] = []
    for row in rows:
        if exclude_id and row.id == exclude_id:
            continue
        updated = getattr(row, "updated_at", None)
        if start and updated is not None and updated < start:
            continue
        if end and updated is not None:
            end_exclusive = end.replace(hour=23, minute=59, second=59)
            if updated > end_exclusive:
                continue
        title = (getattr(row, "title", None) or "New chat").strip() or "New chat"
        first = grok_store.first_user_message_content(db, row.id) or ""
        if needle and needle not in title.lower() and needle not in first.lower():
            continue
        last = grok_store.last_message_content(db, row.id) or ""
        summary = clip(first) or "(no messages yet)"
        if last and last.strip() != first.strip():
            tail = clip(last, 120)
            if tail:
                summary = clip(f"{summary} Last: {tail}", SUMMARY_CHAR + 40)
        note_id = getattr(row, "saved_note_id", None)
        out.append(
            {
                "id": str(row.id),
                "date": _day(updated),
                "title": clip(title, 80),
                "summary": summary,
                "note_id": str(note_id) if note_id else None,
                "messages": grok_store.message_count(db, row.id),
            }
        )
        if len(out) >= limit:
            break
    return out


def format_index(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"{INDEX_HEADER}\nNone."
    lines = [INDEX_HEADER]
    for row in rows:
        note = row.get("note_id") or "none"
        lines.append(
            f"- {row.get('date') or 'unknown'} · {row.get('title') or 'New chat'} · "
            f"id={row.get('id')} · note={note} · {int(row.get('messages') or 0)} messages"
        )
        summary = (row.get("summary") or "").strip()
        if summary:
            lines.append(f"  {summary}")
    lines.append("Open one thread with read_chat and that id. Do not invent chats missing from this list.")
    return "\n".join(lines)


def read_slice(
    db: Session,
    user: User,
    conversation_id: UUID,
    *,
    offset: int = 0,
) -> dict[str, Any]:
    start = max(0, int(offset or 0))
    conversation = grok_store.get_conversation(db, user, conversation_id)
    history = grok_store.conversation_history(db, conversation.id)
    total = len(history)
    window = history[start : start + READ_MESSAGE_CAP]
    used = 0
    turns: list[dict[str, str]] = []
    for item in window:
        role = str(item.get("role") or "user")
        body = clip(str(item.get("content") or ""), READ_CHAR_CAP)
        files = item.get("files") or []
        names = [str(file.get("filename") or "file") for file in files if isinstance(file, dict)]
        if names:
            body = clip(f"{body} [files: {', '.join(names)}]", READ_CHAR_CAP)
        next_used = used + len(body)
        if turns and next_used > READ_CHAR_CAP:
            break
        turns.append({"role": role, "content": body[: max(0, READ_CHAR_CAP - used)]})
        used += len(turns[-1]["content"])
        if used >= READ_CHAR_CAP:
            break
    next_offset = start + len(turns)
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "note_id": str(conversation.saved_note_id) if conversation.saved_note_id else None,
        "offset": start,
        "next_offset": next_offset if next_offset < total else None,
        "total": total,
        "turns": turns,
    }


def format_slice(payload: dict[str, Any]) -> str:
    title = payload.get("title") or "New chat"
    note = payload.get("note_id") or "none"
    total = int(payload.get("total") or 0)
    offset = int(payload.get("offset") or 0)
    nxt = payload.get("next_offset")
    turns = payload.get("turns") or []
    lines = [
        f"Junior chat slice: {title} · id={payload.get('id')} · note={note} · "
        f"messages {offset + 1}–{offset + len(turns)} of {total}."
    ]
    if not turns:
        lines.append("No messages in this slice.")
    for item in turns:
        role = "Steve" if item.get("role") == "user" else "Junior"
        lines.append(f"- {role}: {item.get('content') or ''}")
    if nxt is not None:
        lines.append(f"Truncated. Next slice offset={nxt}. Summarize; do not paste everything.")
    else:
        lines.append("End of this thread. Do not invent later messages.")
    return "\n".join(lines)


def assemble_tool_call(fragments: list[dict] | None) -> dict[str, Any] | None:
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
        name = slot.get("name") or ""
        if name not in {LIST_NAME, READ_NAME}:
            continue
        try:
            parsed = json.loads(slot.get("arguments") or "{}")
        except json.JSONDecodeError:
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
        if name == LIST_NAME:
            return {
                "name": LIST_NAME,
                "q": clip(str(parsed.get("q") or parsed.get("query") or ""), QUERY_CHAR_CAP),
                "from_date": str(parsed.get("from_date") or parsed.get("from") or "")[:10],
                "to_date": str(parsed.get("to_date") or parsed.get("to") or "")[:10],
            }
        raw_id = str(parsed.get("conversation_id") or parsed.get("id") or "").strip()
        try:
            conversation_id = UUID(raw_id)
        except ValueError:
            return {"name": READ_NAME, "conversation_id": None, "offset": 0}
        try:
            offset = int(parsed.get("offset") or 0)
        except (TypeError, ValueError):
            offset = 0
        return {"name": READ_NAME, "conversation_id": conversation_id, "offset": max(0, offset)}
    return None


def execute_tool(db: Session, user: User, call: dict[str, Any], *, current_id: UUID | None = None) -> str:
    name = call.get("name")
    if name == LIST_NAME:
        rows = build_index(
            db,
            user,
            query=str(call.get("q") or "") or None,
            from_date=str(call.get("from_date") or "") or None,
            to_date=str(call.get("to_date") or "") or None,
            exclude_id=None,
        )
        return format_index(rows)
    conversation_id = call.get("conversation_id")
    if not isinstance(conversation_id, UUID):
        return "No chat with that id. Use the index. Do not invent a thread."
    try:
        payload = read_slice(db, user, conversation_id, offset=int(call.get("offset") or 0))
    except HTTPException:
        return "No chat with that id. Use the index. Do not invent a thread."
    if current_id and conversation_id == current_id:
        return f"{format_slice(payload)}\nThis is the current thread; prefer the live window unless he asked to reread it."
    return format_slice(payload)


def execute_tool_for_user(user_id: UUID, current_id: UUID | None, call: dict[str, Any]) -> str:
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or not can_use(user):
            return "Chat index is not enabled on this account."
        return execute_tool(db, user, call, current_id=current_id)
