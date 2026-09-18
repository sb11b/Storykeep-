from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.services import junior_memory

SLICE_MESSAGE_CAP = 20
SLICE_TOKEN_CAP = 8000
CHARS_PER_TOKEN = 4
JUNIOR_THREAD_WINDOW = 8

_SPEC_DOC_RE = re.compile(
    r"\b(?:TIMELINE|UI_NOTES|UI NOTES|ARCHITECTURE|DATA_MODEL|PHASE1|PHASE2|MERIDIAN)\b",
    re.I,
)
_SPEC_SECTION_RE = re.compile(
    r"(?im)^#+\s*(?:TIMELINE|UI[_ ]NOTES|ARCHITECTURE|DATA[_ ]MODEL|PHASE\s*[12]|MERIDIAN).*$"
)
_CURSOR_SECTION_RE = re.compile(r"(?im)^#+\s*.*\bCURSOR\b.*$")
_ASK_CURSOR_PROMPT_RE = re.compile(
    r"\b(?:write|draft|generate|create|give me|need|make|want)\s+(?:me\s+)?(?:a\s+)?"
    r"(?:prompt for (?:the\s+)?cursor|cursor prompt|cursor agent prompt|cloud agent prompt)\b|"
    r"\b(?:prompt for (?:the\s+)?cursor|cursor agent prompt|cloud agent prompt)\s+(?:for|to)\b",
    re.I,
)
_TASK_VERB_RE = re.compile(
    r"\b(?:fix|implement|add|ensure|update|refactor|investigate|debug|deploy|complete|remove|change)\b",
    re.I,
)
_CURSOR_TASK_MARKERS_RE = re.compile(
    r"\b(?:done when|acceptance criteria|success criteria|files? to touch|repo context)\b|"
    r"(?:frontend|backend)/[\w./-]+|\b[\w-]+\.(?:tsx?|py|md)\b",
    re.I,
)
_DATABASE_CURSOR_RE = re.compile(r"\b(?:database|sql|postgres|mysql|sqlite)\s+cursor\b", re.I)

CURSOR_PROMPT_APPEND = """
Steve asked you to write a Cursor / Cloud Agent prompt. Reply with ONE complete copy-paste block he can drop into Cursor.
Include: goal, repo or file context, constraints, files or areas to touch, and clear done-when criteria.
Do not web-search, list chats, or wander into spec docs. Do not truncate or split across turns.
"""

CURSOR_PROMPT_DETAILS_APPEND = """
Steve already gave task details (typed or dictated). Fold every detail into the copy-paste block — do not replace or narrow his scope.
"""

CURSOR_FOLLOW_APPEND = """
Steve supplied the Cursor / Cloud Agent task himself (typed or dictated). Stay on his scope.
Reply with ONE polished copy-paste prompt block derived from his text — not a new plan or investigation.
Do not web-search, list chats, read spec docs, or claim you changed the repo unless he asked.
Do not execute the task in this reply. Finish in one reply.
"""


def estimate_tokens(text: str) -> int:
    return max(1, len(text or "") // CHARS_PER_TOKEN)


def wants_spec_docs(message: str) -> bool:
    return bool(_SPEC_DOC_RE.search(message or ""))


def asks_for_cursor_prompt(message: str) -> bool:
    """Steve wants Junior to generate a Cursor agent prompt."""
    text = (message or "").strip()
    if not text or _DATABASE_CURSOR_RE.search(text):
        return False
    if _ASK_CURSOR_PROMPT_RE.search(text):
        return True
    if len(text) >= 260:
        return False
    asks = bool(re.search(r"\b(?:write|draft|generate|give|need|make|create|want)\b", text, re.I))
    cursor = bool(
        re.search(r"\b(?:prompt for (?:the\s+)?cursor|cursor prompt|cloud agent)\b", text, re.I)
    )
    return asks and cursor


def cursor_prompt_has_task_details(message: str) -> bool:
    """Generate request already embeds the task (common after STT)."""
    text = (message or "").strip()
    if not asks_for_cursor_prompt(text):
        return False
    if ":" in text:
        head, tail = text.split(":", 1)
        if len(head) < 120 and len(tail.strip()) >= 24:
            return True
    return bool(_TASK_VERB_RE.search(text) and len(text) >= 80)


def brings_cursor_task(message: str) -> bool:
    """Steve supplied the agent task — polish/follow it, do not invent a new one."""
    text = (message or "").strip()
    if not text or asks_for_cursor_prompt(text):
        return False
    if len(text) < 100 or not _TASK_VERB_RE.search(text):
        return False
    structured = bool(re.search(r"(?:^|\n)(?:#+\s+|[-*]\s+|\d+\.)", text, re.M))
    if structured:
        return True
    if _CURSOR_TASK_MARKERS_RE.search(text):
        return True
    if len(_TASK_VERB_RE.findall(text)) >= 2 and len(text) >= 100:
        return True
    return len(text) >= 220


def cursor_turn_mode(message: str) -> str | None:
    """generate | follow | None"""
    if asks_for_cursor_prompt(message):
        return "generate"
    if brings_cursor_task(message):
        return "follow"
    return None


def is_cursor_task_turn(message: str) -> bool:
    return cursor_turn_mode(message) is not None


def filter_standing_memory(body: str, *, user_text: str) -> str:
    """Drop spec-doc sections from memory unless Steve's turn is about them."""
    text = (body or "").strip()
    if not text or wants_spec_docs(user_text):
        return text
    lines = text.splitlines()
    kept: list[str] = []
    skip = False
    for line in lines:
        stripped = line.strip()
        if _CURSOR_SECTION_RE.match(stripped):
            skip = False
            kept.append(line)
            continue
        if _SPEC_SECTION_RE.match(stripped):
            skip = True
            continue
        if skip and line.startswith("#"):
            skip = False
        if not skip:
            kept.append(line)
    return "\n".join(kept).strip()


def standing_system(
    db: Session,
    user: User,
    *,
    user_text: str,
    core_prompt: str,
    extras: list[str] | None = None,
) -> str:
    """Standing memory + core Junior prompt + only turn-relevant extras."""
    parts: list[str] = [core_prompt.strip()]
    memory = junior_memory.system_section(db, user)
    if memory:
        prefix, _, body = memory.partition("\n")
        filtered = filter_standing_memory(body, user_text=user_text)
        if filtered:
            parts.append(f"{prefix}\n{filtered}".strip() if prefix else filtered)
    for block in extras or []:
        bit = (block or "").strip()
        if bit:
            parts.append(bit)
    return "\n\n".join(parts)


def cap_slice_messages(messages: list[dict[str, Any]]) -> tuple[list[dict[str, str]], bool]:
    """Last 20 messages or ~8k tokens, whichever is smaller. Prefer newest on token cap."""
    if not messages:
        return [], False
    truncated = len(messages) > SLICE_MESSAGE_CAP
    recent = messages[-SLICE_MESSAGE_CAP:]
    picked: list[dict[str, str]] = []
    tokens = 0
    for item in reversed(recent):
        role = str(item.get("role") or "user")
        if role not in {"user", "assistant"}:
            role = "user"
        body = str(item.get("content") or "")
        need = estimate_tokens(body)
        if picked and tokens + need > SLICE_TOKEN_CAP:
            truncated = True
            break
        if tokens + need > SLICE_TOKEN_CAP:
            room = max(0, (SLICE_TOKEN_CAP - tokens) * CHARS_PER_TOKEN)
            body = body[:room].rstrip()
            truncated = True
            need = estimate_tokens(body)
        if not body and not picked:
            continue
        picked.insert(0, {"role": role, "content": body})
        tokens += need
        if tokens >= SLICE_TOKEN_CAP:
            break
    return picked, truncated


def format_index_for_model(rows: list[dict[str, Any]]) -> str:
    """id, date, title, one-line summary — never bodies or counts."""
    if not rows:
        return "Junior chat index: none."
    lines = ["Junior chat index (id, date, title, summary):"]
    for row in rows:
        summary = " ".join(str(row.get("summary") or "").split())
        lines.append(
            f"- id={row.get('id')} · {row.get('date') or 'unknown'} · "
            f"{row.get('title') or 'New chat'} · {summary or '(no summary)'}"
        )
    lines.append("Open one thread with read_chat and that id.")
    return "\n".join(lines)


def model_payload(
    *,
    user_text: str,
    slice: dict[str, Any],
    standing_memory: str,
) -> list[dict[str, str]]:
    """Standing memory + one read_chat slice + current user line."""
    rows = slice.get("messages") or slice.get("turns") or []
    window, _ = cap_slice_messages(rows)
    system = standing_memory
    if slice.get("truncated"):
        system += "\n\n[Slice truncated=true. Summarize what you have; ask Steve for the next offset.]"
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    messages.extend(window)
    messages.append({"role": "user", "content": user_text})
    return messages


def chats_turn_active(user_text: str, *, indexed: bool, read: bool, tools: bool) -> bool:
    from app.services import chat_index

    return indexed or read or tools or chat_index.wants_index(user_text) or chat_index.wants_read(user_text)


def build_turn_extras(
    user_text: str,
    *,
    memory_block: str | None,
    chats_enabled: bool,
    index_block: str | None,
    read_meta: str | None,
    unread_catalog: str | None,
    calendar_connected: bool,
    calendar_tools: bool,
    mail_connected: bool,
    mail_unread: bool,
    unread_mail_md: str | None,
    search_enabled: bool,
    will_search: bool,
) -> list[str]:
    """Attach only what this turn needs. Never dump spec docs or full chat bodies."""
    del memory_block  # standing memory lives in standing_system(), not extras
    extras: list[str] = []
    from app.services import chat_index
    from app.services import mail_tool
    from app.services import web_search as search_tool
    from app.services.calendar_tool import CALENDAR_OFF_APPEND, CALENDAR_ON_APPEND

    cursor_task = is_cursor_task_turn(user_text)
    chat_tools = chats_enabled and not cursor_task and chats_turn_active(
        user_text,
        indexed=bool(index_block),
        read=bool(read_meta),
        tools=calendar_tools or mail_unread or will_search,
    )
    if chat_tools:
        extras.append(chat_index.CHATS_ON_APPEND)
    if index_block:
        extras.append(index_block)
    if read_meta:
        extras.append(read_meta)
    if unread_catalog:
        from app.services.junior_jobs import UNREAD_READER_SYSTEM

        extras.append(UNREAD_READER_SYSTEM)
    if calendar_tools:
        extras.append(CALENDAR_ON_APPEND if calendar_connected else CALENDAR_OFF_APPEND)
    if mail_unread:
        extras.append(mail_tool.UNREAD_MAIL_SYSTEM)
        if unread_mail_md:
            extras.append(unread_mail_md)
    elif mail_connected and mail_tool.wants_send_mail(user_text):
        extras.append(mail_tool.MAIL_ON_APPEND)
    if search_enabled and not cursor_task:
        from app.services import chat as chat_service

        if will_search or not chat_service.is_small_talk_turn(user_text):
            extras.append(search_tool.SEARCH_ON_APPEND)
    mode = cursor_turn_mode(user_text)
    if mode == "generate":
        extras.append(CURSOR_PROMPT_APPEND)
        if cursor_prompt_has_task_details(user_text):
            extras.append(CURSOR_PROMPT_DETAILS_APPEND)
    elif mode == "follow":
        extras.append(CURSOR_FOLLOW_APPEND)
    return extras
