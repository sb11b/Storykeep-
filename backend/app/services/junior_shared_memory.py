from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    JuniorAgentRun,
    JuniorMemoryFact,
    JuniorProject,
    JuniorSession,
    JuniorThread,
    JuniorThreadMessage,
    User,
)

VENUES = frozenset({"storykeep", "phone", "windows", "voice"})
ROLES = frozenset({"user", "junior", "system"})
MEMORY_KINDS = frozenset({"profile", "preference", "decision", "note"})
THREAD_STATUSES = frozenset({"open", "archived"})
TITLE_MAX = 120
CONTENT_MAX = 32_000
MEMORY_CONTENT_MAX = 8_000
HISTORY_WINDOW = 24
SUMMARY_EVERY = 8
REMEMBER_WHEN = re.compile(r"\bremember when\b", re.I)
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PROJECT_KINDS = frozenset({"app", "api", "overlay", "infra", "other"})
AGENT_STATUSES = frozenset({"context_ready", "launched", "failed", "cancelled"})
OWNER_EMAIL = "angry.tune8751@fastmail.com"

SEED_PROJECTS: tuple[dict[str, Any], ...] = (
    {
        "slug": "storykeep",
        "display_name": "StoryKeep",
        "kind": "app",
        "repo_url": "https://cursor.com/codebase/steve-bitsko/Storykeep",
        "default_branch": "main",
        "notes": (
            "StoryKeep web + Junior Memory API live here for now. "
            "Phone and overlay are clients of this same API, not a second database."
        ),
        "meta": {"venue": "storykeep"},
    },
    {
        "slug": "junior-phone",
        "display_name": "Junior mobile",
        "kind": "app",
        "repo_url": "https://cursor.com/codebase/steve-bitsko/junior-mobile",
        "default_branch": "main",
        "notes": (
            "Junior mobile (phone) Expo client of the same Memory API. "
            "Use venue=phone on threads/messages. Talks to StoryKeep /api/v1/junior/*. "
            "No separate phone DB. Origin repo: https://cursor.com/codebase/steve-bitsko/junior-mobile"
        ),
        "meta": {
            "venue": "phone",
            "stack": "expo",
            "client": "expo-phone",
            "api": "/api/v1/junior/*",
        },
    },
    {
        "slug": "windows-overlay",
        "display_name": "Windows overlay",
        "kind": "overlay",
        "repo_url": None,
        "default_branch": "main",
        "notes": "Always-on Windows overlay. Placeholder until a repo exists. venue=windows.",
        "meta": {"venue": "windows", "repo": "placeholder"},
    },
)

SEED_DECISIONS: tuple[str, ...] = (
    "Railway Postgres is the source of truth for Junior chat history, search, and durable facts. Not xAI.",
    "xAI is inference only — generate replies; do not hold history.",
    "StoryKeep (web), the Junior phone app, and the Windows overlay share one Memory API and the same user_id. venue=phone is first-class.",
    "Junior can launch Cursor agents with a project registry + agent-context pack (repo, thread, memories) — not StoryKeep-only.",
)

REPLY_STUB_DETAIL = (
    "User message was saved in Railway Postgres. Junior reply generation needs "
    "XAI_API_KEY (xAI is inference only — history stays in Postgres). "
    "TODO: if this status is stubbed_todo, complete_once was not reached; "
    "context (last N, summary, memories, optional FTS) is already packed."
)


@dataclass
class TurnContext:
    history: list[JuniorThreadMessage] = field(default_factory=list)
    memories: list[JuniorMemoryFact] = field(default_factory=list)
    search_hits: list[dict[str, Any]] = field(default_factory=list)
    xai_messages: list[dict[str, str]] = field(default_factory=list)


def normalize_venue(value: str | None) -> str:
    venue = (value or "storykeep").strip().lower()
    if venue not in VENUES:
        raise HTTPException(status_code=400, detail="Invalid venue")
    return venue


def normalize_kind(value: str | None) -> str:
    kind = (value or "note").strip().lower()
    if kind not in MEMORY_KINDS:
        raise HTTPException(status_code=400, detail="Invalid memory kind")
    return kind


def normalize_status(value: str | None) -> str:
    status_value = (value or "open").strip().lower()
    if status_value not in THREAD_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid thread status")
    return status_value


def _clean_text(value: str | None, *, max_len: int, required: bool = True) -> str:
    text = (value or "").replace("\x00", "").strip()
    if required and not text:
        raise HTTPException(status_code=400, detail="Content is required")
    if len(text) > max_len:
        raise HTTPException(status_code=400, detail="Text is too long")
    return text


def wants_recall(text: str) -> bool:
    return bool(REMEMBER_WHEN.search(text or ""))


def thread_owned(db: Session, user: User, thread_id: UUID) -> JuniorThread:
    row = db.get(JuniorThread, thread_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    return row


def memory_owned(db: Session, user: User, memory_id: UUID) -> JuniorMemoryFact:
    row = db.get(JuniorMemoryFact, memory_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return row


def thread_memory_owned(
    db: Session, user: User, thread_id: UUID, memory_id: UUID
) -> JuniorMemoryFact:
    thread_owned(db, user, thread_id)
    row = memory_owned(db, user, memory_id)
    if row.source_thread != thread_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return row


def session_owned(db: Session, user: User, session_id: UUID) -> JuniorSession:
    row = db.get(JuniorSession, session_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return row


def message_owned(db: Session, user: User, message_id: UUID) -> JuniorThreadMessage:
    row = db.get(JuniorThreadMessage, message_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    thread = db.get(JuniorThread, row.thread_id)
    if thread is None or thread.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return row


def thread_message_owned(
    db: Session, user: User, thread_id: UUID, message_id: UUID
) -> JuniorThreadMessage:
    thread_owned(db, user, thread_id)
    row = message_owned(db, user, message_id)
    if row.thread_id != thread_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return row


def update_thread_message(
    db: Session,
    user: User,
    thread_id: UUID,
    message_id: UUID,
    *,
    content: str | None = None,
    venue: str | None = None,
    meta: dict[str, Any] | None = None,
    set_venue: bool = False,
    set_meta: bool = False,
) -> JuniorThreadMessage:
    thread_message_owned(db, user, thread_id, message_id)
    return update_message(
        db,
        user,
        message_id,
        content=content,
        venue=venue,
        meta=meta,
        set_venue=set_venue,
        set_meta=set_meta,
    )


def update_message(
    db: Session,
    user: User,
    message_id: UUID,
    *,
    content: str | None = None,
    venue: str | None = None,
    meta: dict[str, Any] | None = None,
    set_venue: bool = False,
    set_meta: bool = False,
) -> JuniorThreadMessage:
    row = message_owned(db, user, message_id)
    if content is not None:
        row.content = _clean_text(content, max_len=CONTENT_MAX)
    if set_venue and venue is not None:
        row.venue = normalize_venue(venue)
    if set_meta and meta is not None:
        row.meta = meta
    db.flush()
    return row


def update_session(
    db: Session,
    user: User,
    session_id: UUID,
    *,
    venue: str | None = None,
    device_label: str | None = None,
    set_device_label: bool = False,
) -> JuniorSession:
    row = session_owned(db, user, session_id)
    if venue is not None:
        row.venue = normalize_venue(venue)
    if set_device_label:
        row.device_label = _clean_text(device_label, max_len=120, required=False) or None
    row.last_seen_at = datetime.now(timezone.utc)
    db.flush()
    return row


def update_thread(
    db: Session,
    user: User,
    thread_id: UUID,
    *,
    title: str | None = None,
    status_value: str | None = None,
) -> JuniorThread:
    row = thread_owned(db, user, thread_id)
    if title is not None:
        row.title = _clean_text(title, max_len=TITLE_MAX, required=False) or None
    if status_value is not None:
        row.status = normalize_status(status_value)
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return row


def last_open_thread(db: Session, user: User) -> JuniorThread | None:
    return db.scalar(
        select(JuniorThread)
        .where(JuniorThread.user_id == user.id, JuniorThread.status == "open")
        .order_by(JuniorThread.updated_at.desc())
        .limit(1)
    )


def resolve_thread(
    db: Session,
    user: User,
    thread_id: UUID | None,
    venue: str | None,
) -> JuniorThread:
    if thread_id is not None:
        return thread_owned(db, user, thread_id)
    existing = last_open_thread(db, user)
    if existing is not None:
        return existing
    return create_thread(db, user, title=None, venue=venue)


PAGE_MAX = 100
PAGE_DEFAULT = 50


def clamp_page_limit(limit: int | None, *, default: int = PAGE_DEFAULT) -> int:
    if limit is None:
        return default
    return max(1, min(int(limit), PAGE_MAX))


def _as_uuid(value: UUID | str | None) -> UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _item_id(item: Any, id_attr: str) -> Any:
    if isinstance(item, dict):
        return item.get(id_attr)
    return getattr(item, id_attr, None)


def paginate_items(
    items: list[Any],
    *,
    limit: int | None = PAGE_DEFAULT,
    cursor: UUID | str | None = None,
    before_id: UUID | str | None = None,
    id_attr: str = "id",
) -> tuple[list[Any], str | None]:
    """In-memory page: skip the marker id, then take `limit`. Used by tests and clients."""
    cap = clamp_page_limit(limit)
    marker = _as_uuid(before_id) or _as_uuid(cursor)
    rows = list(items)
    if marker is not None:
        ids = [_as_uuid(_item_id(item, id_attr)) for item in rows]
        if marker in ids:
            rows = rows[ids.index(marker) + 1 :]
    page = rows[:cap]
    next_id = _item_id(page[-1], id_attr) if len(rows) > cap and page else None
    next_cursor = str(next_id) if next_id is not None else None
    return page, next_cursor


def list_threads(
    db: Session,
    user: User,
    *,
    limit: int = PAGE_DEFAULT,
    cursor: UUID | str | None = None,
    before_id: UUID | str | None = None,
) -> list[JuniorThread]:
    rows, _ = list_threads_page(db, user, limit=limit, cursor=cursor, before_id=before_id)
    return rows


def list_threads_page(
    db: Session,
    user: User,
    *,
    limit: int = PAGE_DEFAULT,
    cursor: UUID | str | None = None,
    before_id: UUID | str | None = None,
) -> tuple[list[JuniorThread], str | None]:
    cap = clamp_page_limit(limit)
    stmt = select(JuniorThread).where(JuniorThread.user_id == user.id)
    marker = _as_uuid(before_id) or _as_uuid(cursor)
    if marker is not None:
        ref = db.scalar(
            select(JuniorThread).where(JuniorThread.user_id == user.id, JuniorThread.id == marker)
        )
        if ref is not None:
            stmt = stmt.where(
                or_(
                    JuniorThread.updated_at < ref.updated_at,
                    and_(JuniorThread.updated_at == ref.updated_at, JuniorThread.id < ref.id),
                )
            )
    stmt = stmt.order_by(JuniorThread.updated_at.desc(), JuniorThread.id.desc()).limit(cap + 1)
    rows = list(db.scalars(stmt))
    has_more = len(rows) > cap
    page = rows[:cap]
    next_cursor = str(page[-1].id) if has_more and page else None
    return page, next_cursor


def create_thread(
    db: Session,
    user: User,
    *,
    title: str | None,
    venue: str | None,
    status_value: str | None = "open",
) -> JuniorThread:
    now = datetime.now(timezone.utc)
    row = JuniorThread(
        user_id=user.id,
        title=_clean_text(title, max_len=TITLE_MAX, required=False) or None,
        venue_last=normalize_venue(venue),
        status=normalize_status(status_value),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def list_messages(
    db: Session,
    user: User,
    thread_id: UUID,
    *,
    limit: int | None = None,
    cursor: UUID | str | None = None,
    before_id: UUID | str | None = None,
) -> list[JuniorThreadMessage]:
    rows, _ = list_messages_page(
        db, user, thread_id, limit=limit, cursor=cursor, before_id=before_id
    )
    return rows


def list_messages_page(
    db: Session,
    user: User,
    thread_id: UUID,
    *,
    limit: int | None = None,
    cursor: UUID | str | None = None,
    before_id: UUID | str | None = None,
) -> tuple[list[JuniorThreadMessage], str | None]:
    thread_owned(db, user, thread_id)
    marker = _as_uuid(before_id) or _as_uuid(cursor)
    if limit is None and marker is None:
        stmt = (
            select(JuniorThreadMessage)
            .where(JuniorThreadMessage.thread_id == thread_id)
            .order_by(JuniorThreadMessage.created_at.asc(), JuniorThreadMessage.id.asc())
        )
        return list(db.scalars(stmt)), None

    cap = clamp_page_limit(limit)
    filters = [JuniorThreadMessage.thread_id == thread_id]
    if marker is not None:
        ref = db.scalar(
            select(JuniorThreadMessage).where(
                JuniorThreadMessage.thread_id == thread_id,
                JuniorThreadMessage.id == marker,
            )
        )
        if ref is not None:
            filters.append(
                or_(
                    JuniorThreadMessage.created_at < ref.created_at,
                    and_(
                        JuniorThreadMessage.created_at == ref.created_at,
                        JuniorThreadMessage.id < ref.id,
                    ),
                )
            )
    stmt = (
        select(JuniorThreadMessage)
        .where(*filters)
        .order_by(JuniorThreadMessage.created_at.desc(), JuniorThreadMessage.id.desc())
        .limit(cap + 1)
    )
    newest_first = list(db.scalars(stmt))
    has_more = len(newest_first) > cap
    page = list(reversed(newest_first[:cap]))
    next_cursor = str(page[0].id) if has_more and page else None
    return page, next_cursor


def list_recent_messages_page(
    db: Session,
    user: User,
    *,
    limit: int = PAGE_DEFAULT,
    cursor: UUID | str | None = None,
    before_id: UUID | str | None = None,
    thread_id: UUID | None = None,
) -> tuple[list[JuniorThreadMessage], str | None]:
    if thread_id is not None:
        return list_messages_page(
            db, user, thread_id, limit=limit, cursor=cursor, before_id=before_id
        )
    cap = clamp_page_limit(limit)
    stmt = (
        select(JuniorThreadMessage)
        .join(JuniorThread, JuniorThreadMessage.thread_id == JuniorThread.id)
        .where(JuniorThread.user_id == user.id)
    )
    marker = _as_uuid(before_id) or _as_uuid(cursor)
    if marker is not None:
        ref = db.scalar(select(JuniorThreadMessage).where(JuniorThreadMessage.id == marker))
        if ref is not None:
            stmt = stmt.where(
                or_(
                    JuniorThreadMessage.created_at < ref.created_at,
                    and_(
                        JuniorThreadMessage.created_at == ref.created_at,
                        JuniorThreadMessage.id < ref.id,
                    ),
                )
            )
    stmt = stmt.order_by(
        JuniorThreadMessage.created_at.desc(), JuniorThreadMessage.id.desc()
    ).limit(cap + 1)
    newest_first = list(db.scalars(stmt))
    has_more = len(newest_first) > cap
    page = newest_first[:cap]
    next_cursor = str(page[-1].id) if has_more and page else None
    return page, next_cursor


def touch_session(db: Session, user: User, venue: str, device_label: str | None) -> JuniorSession:
    now = datetime.now(timezone.utc)
    venue_value = normalize_venue(venue)
    label = _clean_text(device_label, max_len=120, required=False) or None
    existing = db.scalar(
        select(JuniorSession)
        .where(
            JuniorSession.user_id == user.id,
            JuniorSession.venue == venue_value,
            JuniorSession.device_label.is_(None) if label is None else JuniorSession.device_label == label,
        )
        .order_by(JuniorSession.last_seen_at.desc())
        .limit(1)
    )
    if existing is None:
        row = JuniorSession(
            user_id=user.id,
            venue=venue_value,
            device_label=label,
            last_seen_at=now,
            created_at=now,
        )
        db.add(row)
        db.flush()
        return row
    existing.last_seen_at = now
    db.flush()
    return existing


def list_sessions_page(
    db: Session,
    user: User,
    *,
    limit: int | None = PAGE_DEFAULT,
    cursor: UUID | str | None = None,
    before_id: UUID | str | None = None,
    venue: str | None = None,
) -> tuple[list[JuniorSession], str | None]:
    cap = clamp_page_limit(limit)
    stmt = select(JuniorSession).where(JuniorSession.user_id == user.id)
    if venue:
        stmt = stmt.where(JuniorSession.venue == normalize_venue(venue))
    marker = _as_uuid(before_id) or _as_uuid(cursor)
    if marker is not None:
        ref = db.scalar(
            select(JuniorSession).where(
                JuniorSession.user_id == user.id, JuniorSession.id == marker
            )
        )
        if ref is not None:
            stmt = stmt.where(
                or_(
                    JuniorSession.last_seen_at < ref.last_seen_at,
                    and_(
                        JuniorSession.last_seen_at == ref.last_seen_at,
                        JuniorSession.id < ref.id,
                    ),
                )
            )
    stmt = stmt.order_by(
        JuniorSession.last_seen_at.desc(), JuniorSession.id.desc()
    ).limit(cap + 1)
    rows = list(db.scalars(stmt))
    has_more = len(rows) > cap
    page = rows[:cap]
    next_cursor = str(page[-1].id) if has_more and page else None
    return page, next_cursor


def recent_thread_context(db: Session, thread: JuniorThread) -> list[JuniorThreadMessage]:
    stmt = (
        select(JuniorThreadMessage)
        .where(JuniorThreadMessage.thread_id == thread.id)
        .order_by(JuniorThreadMessage.created_at.desc(), JuniorThreadMessage.id.desc())
        .limit(HISTORY_WINDOW)
    )
    rows = list(db.scalars(stmt) or [])
    rows.reverse()
    return rows


def top_memories(db: Session, user: User, *, limit: int = 12) -> list[JuniorMemoryFact]:
    stmt = (
        select(JuniorMemoryFact)
        .where(JuniorMemoryFact.user_id == user.id)
        .order_by(JuniorMemoryFact.updated_at.desc())
        .limit(max(1, min(limit, 50)))
    )
    return list(db.scalars(stmt) or [])


def message_count(db: Session, thread_id: UUID) -> int:
    return int(
        db.scalar(select(func.count()).select_from(JuniorThreadMessage).where(JuniorThreadMessage.thread_id == thread_id))
        or 0
    )


def maybe_refresh_summary(db: Session, thread: JuniorThread) -> None:
    count = message_count(db, thread.id)
    if count == 0 or count % SUMMARY_EVERY != 0:
        return
    recent = recent_thread_context(db, thread)
    bits = [((row.content or "").strip()[:80]) for row in recent[-4:] if (row.content or "").strip()]
    if bits:
        thread.summary = " · ".join(bits)[:500]


def build_turn_context(db: Session, user: User, thread: JuniorThread, user_text: str) -> TurnContext:
    history = recent_thread_context(db, thread)
    memories = top_memories(db, user)
    hits: list[dict[str, Any]] = []
    if wants_recall(user_text):
        try:
            hits = search(db, user, user_text, limit=5)
        except HTTPException:
            hits = []
    system_parts = [
        "You are Junior. Durable history is in Postgres, not in this prompt.",
        "Do not invent threads the user did not mention.",
    ]
    if (thread.summary or "").strip():
        system_parts.append(f"Thread summary: {thread.summary.strip()}")
    if memories:
        facts = "\n".join(f"- ({row.kind}) {row.content}" for row in memories)
        system_parts.append(f"Standing facts:\n{facts}")
    if hits:
        snippets = "\n".join(f"- {hit.get('thread_title') or 'chat'}: {hit.get('snippet')}" for hit in hits)
        system_parts.append(f"Recall hits:\n{snippets}")
    packed: list[dict[str, str]] = [{"role": "system", "content": "\n\n".join(system_parts)}]
    for row in history:
        if row.role == "system":
            continue
        packed.append(
            {
                "role": "assistant" if row.role == "junior" else "user",
                "content": row.content,
            }
        )
    return TurnContext(history=history, memories=memories, search_hits=hits, xai_messages=packed)


def call_xai_complete(messages: list[dict[str, str]]) -> dict[str, str]:
    """TODO seam: swap or wrap if Junior jobs grow a dedicated memory completion."""
    from app.services.chat import complete_once

    return complete_once(
        messages,
        max_tokens=800,
        timeout_sec=45.0,
        log_slice_id="junior-shared-memory",
    )


def generate_junior_reply(
    db: Session,
    user: User,
    thread: JuniorThread,
    user_text: str = "",
) -> tuple[str | None, str]:
    """Hydrate Postgres context, then call xAI when a key is configured.

    History stays in Railway Postgres. Missing key → no junior row (user turn still saved).
    xAI errors are swallowed so the user message is not rolled back.
    """
    ctx = build_turn_context(db, user, thread, user_text)
    if not (settings.xai_api_key or "").strip():
        return None, "stubbed_no_key"
    try:
        result = call_xai_complete(ctx.xai_messages)
        text = (result.get("text") or "").strip()
        if not text:
            return None, "xai_empty"
        return text, "ok"
    except Exception:
        return None, "xai_error"


def add_user_message(
    db: Session,
    user: User,
    thread_id: UUID,
    *,
    content: str,
    venue: str | None,
    meta: dict[str, Any] | None,
    device_label: str | None = None,
) -> tuple[JuniorThreadMessage, JuniorThreadMessage | None, str]:
    thread = thread_owned(db, user, thread_id)
    venue_value = normalize_venue(venue)
    body = _clean_text(content, max_len=CONTENT_MAX)
    payload = meta if isinstance(meta, dict) else {}
    now = datetime.now(timezone.utc)
    user_row = JuniorThreadMessage(
        thread_id=thread.id,
        role="user",
        content=body,
        venue=venue_value,
        meta=payload,
        created_at=now,
    )
    db.add(user_row)
    if not (thread.title or "").strip():
        thread.title = body[:TITLE_MAX]
    thread.venue_last = venue_value
    thread.updated_at = now
    touch_session(db, user, venue_value, device_label)
    db.flush()

    reply_text, reply_status = generate_junior_reply(db, user, thread, body)
    junior_row = None
    if reply_text:
        junior_row = JuniorThreadMessage(
            thread_id=thread.id,
            role="junior",
            content=reply_text,
            venue=venue_value,
            meta={},
            created_at=datetime.now(timezone.utc),
        )
        db.add(junior_row)
        thread.updated_at = datetime.now(timezone.utc)
        db.flush()
    maybe_refresh_summary(db, thread)
    return user_row, junior_row, reply_status


def post_turn(
    db: Session,
    user: User,
    *,
    thread_id: UUID | None,
    content: str,
    venue: str | None,
    meta: dict[str, Any] | None,
    device_label: str | None = None,
) -> tuple[JuniorThread, JuniorThreadMessage, JuniorThreadMessage | None, str]:
    thread = resolve_thread(db, user, thread_id, venue)
    user_row, junior_row, reply_status = add_user_message(
        db,
        user,
        thread.id,
        content=content,
        venue=venue,
        meta=meta,
        device_label=device_label,
    )
    return thread, user_row, junior_row, reply_status


def search(db: Session, user: User, query: str, *, limit: int = 25) -> list[dict[str, Any]]:
    hits, _ = search_page(db, user, query, limit=limit)
    return hits


def search_page(
    db: Session,
    user: User,
    query: str,
    *,
    limit: int | None = 25,
    cursor: UUID | str | None = None,
    before_id: UUID | str | None = None,
    thread_id: UUID | None = None,
    thread_ids: list[UUID] | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    if thread_ids is not None and not thread_ids:
        return [], None
    q = _clean_text(query, max_len=200)
    cap = clamp_page_limit(limit, default=25)
    tsquery = func.plainto_tsquery("english", q)
    msg_rank = func.ts_rank_cd(JuniorThreadMessage.content_tsv, tsquery)
    thread_rank = func.ts_rank_cd(JuniorThread.title_tsv, tsquery)
    filters = [
        JuniorThread.user_id == user.id,
        or_(
            JuniorThreadMessage.content_tsv.op("@@")(tsquery),
            JuniorThread.title_tsv.op("@@")(tsquery),
        ),
    ]
    if thread_id is not None:
        filters.append(JuniorThread.id == thread_id)
    if thread_ids is not None:
        filters.append(JuniorThread.id.in_(thread_ids))
    stmt = (
        select(JuniorThread, JuniorThreadMessage, msg_rank)
        .join(JuniorThreadMessage, JuniorThreadMessage.thread_id == JuniorThread.id)
        .where(*filters)
        .order_by((msg_rank + thread_rank).desc(), JuniorThread.updated_at.desc(), JuniorThreadMessage.id.desc())
        .limit(PAGE_MAX)
    )
    hits: list[dict[str, Any]] = []
    for thread, message, rank in db.execute(stmt):
        hits.append(_search_hit_dict(thread, message, rank=float(rank or 0)))
    return paginate_items(hits, limit=cap, cursor=cursor, before_id=before_id, id_attr="message_id")


def _search_hit_dict(thread: JuniorThread, message: JuniorThreadMessage, *, rank: float = 0.0) -> dict[str, Any]:
    meta = message.meta if isinstance(getattr(message, "meta", None), dict) else {}
    snippet = str(meta.get("search_snippet") or "").strip() or (message.content or "")[:240]
    return {
        "thread_id": thread.id,
        "thread_title": thread.title,
        "message_id": message.id,
        "snippet": snippet,
        "venue": message.venue,
        "created_at": message.created_at,
        "rank": float(rank or 0),
    }


def search_hit_owned(db: Session, user: User, message_id: UUID) -> dict[str, Any]:
    message = db.get(JuniorThreadMessage, message_id)
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search hit not found")
    thread = db.get(JuniorThread, message.thread_id)
    if thread is None or thread.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search hit not found")
    return _search_hit_dict(thread, message)


def update_search_hit(
    db: Session,
    user: User,
    message_id: UUID,
    *,
    snippet: str | None = None,
    venue: str | None = None,
    set_snippet: bool = False,
    set_venue: bool = False,
) -> dict[str, Any]:
    message = message_owned(db, user, message_id)
    thread = db.get(JuniorThread, message.thread_id)
    if thread is None or thread.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search hit not found")
    meta = dict(message.meta) if isinstance(message.meta, dict) else {}
    if set_snippet:
        cleaned = _clean_text(snippet, max_len=240, required=False)
        if cleaned:
            meta["search_snippet"] = cleaned
        else:
            meta.pop("search_snippet", None)
        message.meta = meta
    if set_venue and venue is not None:
        message.venue = normalize_venue(venue)
    db.flush()
    return _search_hit_dict(thread, message)


def thread_search_hit_owned(db: Session, user: User, thread_id: UUID, message_id: UUID) -> dict[str, Any]:
    thread_owned(db, user, thread_id)
    hit = search_hit_owned(db, user, message_id)
    if hit["thread_id"] != thread_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search hit not found")
    return hit


def update_thread_search_hit(
    db: Session,
    user: User,
    thread_id: UUID,
    message_id: UUID,
    *,
    snippet: str | None = None,
    venue: str | None = None,
    set_snippet: bool = False,
    set_venue: bool = False,
) -> dict[str, Any]:
    thread_search_hit_owned(db, user, thread_id, message_id)
    return update_search_hit(
        db,
        user,
        message_id,
        snippet=snippet,
        venue=venue,
        set_snippet=set_snippet,
        set_venue=set_venue,
    )


def project_search_hit_owned(db: Session, user: User, slug: str, message_id: UUID) -> dict[str, Any]:
    project = get_project(db, user, slug)
    thread_ids = set(project_search_thread_ids(db, user, project))
    hit = search_hit_owned(db, user, message_id)
    if hit["thread_id"] not in thread_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Search hit not found")
    return hit


def project_memory_owned(db: Session, user: User, slug: str, memory_id: UUID) -> JuniorMemoryFact:
    project = get_project(db, user, slug)
    row = memory_owned(db, user, memory_id)
    thread_ids = set(project_search_thread_ids(db, user, project))
    if row.source_thread not in thread_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    return row


def update_project_memory(
    db: Session,
    user: User,
    slug: str,
    memory_id: UUID,
    *,
    content: str | None = None,
    kind: str | None = None,
    source_thread: UUID | None = None,
    set_kind: bool = False,
    set_source_thread: bool = False,
) -> JuniorMemoryFact:
    project_memory_owned(db, user, slug, memory_id)
    return update_memory(
        db,
        user,
        memory_id,
        content=content,
        kind=kind,
        source_thread=source_thread,
        set_kind=set_kind,
        set_source_thread=set_source_thread,
    )


def update_project_search_hit(
    db: Session,
    user: User,
    slug: str,
    message_id: UUID,
    *,
    snippet: str | None = None,
    venue: str | None = None,
    set_snippet: bool = False,
    set_venue: bool = False,
) -> dict[str, Any]:
    project_search_hit_owned(db, user, slug, message_id)
    return update_search_hit(
        db,
        user,
        message_id,
        snippet=snippet,
        venue=venue,
        set_snippet=set_snippet,
        set_venue=set_venue,
    )


def list_memories(db: Session, user: User, *, kind: str | None = None) -> list[JuniorMemoryFact]:
    rows, _ = list_memories_page(db, user, kind=kind)
    return rows


def list_memories_page(
    db: Session,
    user: User,
    *,
    kind: str | None = None,
    source_thread: UUID | None = None,
    limit: int | None = PAGE_DEFAULT,
    cursor: UUID | str | None = None,
    before_id: UUID | str | None = None,
) -> tuple[list[JuniorMemoryFact], str | None]:
    cap = clamp_page_limit(limit)
    stmt = select(JuniorMemoryFact).where(JuniorMemoryFact.user_id == user.id)
    if kind:
        stmt = stmt.where(JuniorMemoryFact.kind == normalize_kind(kind))
    if source_thread is not None:
        stmt = stmt.where(JuniorMemoryFact.source_thread == source_thread)
    marker = _as_uuid(before_id) or _as_uuid(cursor)
    if marker is not None:
        ref_stmt = select(JuniorMemoryFact).where(
            JuniorMemoryFact.user_id == user.id, JuniorMemoryFact.id == marker
        )
        if source_thread is not None:
            ref_stmt = ref_stmt.where(JuniorMemoryFact.source_thread == source_thread)
        ref = db.scalar(ref_stmt)
        if ref is not None:
            stmt = stmt.where(
                or_(
                    JuniorMemoryFact.updated_at < ref.updated_at,
                    and_(
                        JuniorMemoryFact.updated_at == ref.updated_at,
                        JuniorMemoryFact.id < ref.id,
                    ),
                )
            )
    stmt = stmt.order_by(JuniorMemoryFact.updated_at.desc(), JuniorMemoryFact.id.desc()).limit(cap + 1)
    rows = list(db.scalars(stmt))
    has_more = len(rows) > cap
    page = rows[:cap]
    next_cursor = str(page[-1].id) if has_more and page else None
    return page, next_cursor


def upsert_memory(
    db: Session,
    user: User,
    *,
    memory_id: UUID | None,
    kind: str | None,
    content: str,
    source_thread: UUID | None,
) -> JuniorMemoryFact:
    body = _clean_text(content, max_len=MEMORY_CONTENT_MAX)
    kind_value = normalize_kind(kind)
    if source_thread is not None:
        thread_owned(db, user, source_thread)
    now = datetime.now(timezone.utc)
    if memory_id is not None:
        row = db.get(JuniorMemoryFact, memory_id)
        if row is None or row.user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
        row.kind = kind_value
        row.content = body
        row.source_thread = source_thread
        row.updated_at = now
        db.flush()
        return row
    row = JuniorMemoryFact(
        user_id=user.id,
        kind=kind_value,
        content=body,
        source_thread=source_thread,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def create_thread_memory(
    db: Session,
    user: User,
    thread_id: UUID,
    *,
    kind: str | None,
    content: str,
) -> JuniorMemoryFact:
    thread_owned(db, user, thread_id)
    return upsert_memory(
        db,
        user,
        memory_id=None,
        kind=kind,
        content=content,
        source_thread=thread_id,
    )


def update_thread_memory(
    db: Session,
    user: User,
    thread_id: UUID,
    memory_id: UUID,
    *,
    content: str | None = None,
    kind: str | None = None,
    source_thread: UUID | None = None,
    set_kind: bool = False,
    set_source_thread: bool = False,
) -> JuniorMemoryFact:
    thread_memory_owned(db, user, thread_id, memory_id)
    return update_memory(
        db,
        user,
        memory_id,
        content=content,
        kind=kind,
        source_thread=source_thread,
        set_kind=set_kind,
        set_source_thread=set_source_thread,
    )


def update_memory(
    db: Session,
    user: User,
    memory_id: UUID,
    *,
    content: str | None = None,
    kind: str | None = None,
    source_thread: UUID | None = None,
    set_kind: bool = False,
    set_source_thread: bool = False,
) -> JuniorMemoryFact:
    row = memory_owned(db, user, memory_id)
    if content is not None:
        row.content = _clean_text(content, max_len=MEMORY_CONTENT_MAX)
    if set_kind:
        row.kind = normalize_kind(kind)
    if set_source_thread:
        if source_thread is not None:
            thread_owned(db, user, source_thread)
        row.source_thread = source_thread
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return row


def normalize_slug(value: str | None) -> str:
    slug = (value or "").strip().lower()
    if not SLUG_RE.match(slug) or len(slug) > 64:
        raise HTTPException(status_code=400, detail="Invalid project slug")
    return slug


def normalize_kind_project(value: str | None) -> str:
    kind = (value or "other").strip().lower()
    if kind not in PROJECT_KINDS:
        raise HTTPException(status_code=400, detail="Invalid project kind")
    return kind


def list_projects(db: Session, user: User) -> list[JuniorProject]:
    rows, _ = list_projects_page(db, user, limit=PAGE_MAX)
    return rows


def list_projects_page(
    db: Session,
    user: User,
    *,
    limit: int | None = PAGE_DEFAULT,
    cursor: UUID | str | None = None,
    before_id: UUID | str | None = None,
) -> tuple[list[JuniorProject], str | None]:
    cap = clamp_page_limit(limit)
    stmt = select(JuniorProject).where(JuniorProject.user_id == user.id)
    marker = _as_uuid(before_id) or _as_uuid(cursor)
    if marker is not None:
        ref = db.scalar(
            select(JuniorProject).where(
                JuniorProject.user_id == user.id, JuniorProject.id == marker
            )
        )
        if ref is not None:
            stmt = stmt.where(
                or_(
                    JuniorProject.slug > ref.slug,
                    and_(
                        JuniorProject.slug == ref.slug,
                        JuniorProject.id > ref.id,
                    ),
                )
            )
    stmt = stmt.order_by(JuniorProject.slug.asc(), JuniorProject.id.asc()).limit(cap + 1)
    rows = list(db.scalars(stmt))
    has_more = len(rows) > cap
    page = rows[:cap]
    next_cursor = str(page[-1].id) if has_more and page else None
    return page, next_cursor


def project_search_thread_ids(db: Session, user: User, project: JuniorProject) -> list[UUID]:
    """Threads tied to this project: pinned context thread, then agent-run threads."""
    ids: list[UUID] = []
    seen: set[UUID] = set()
    meta = project.meta if isinstance(project.meta, dict) else {}
    pinned = _as_uuid(meta.get("context_thread_id"))
    if pinned is not None:
        thread = db.get(JuniorThread, pinned)
        if thread is not None and thread.user_id == user.id and pinned not in seen:
            seen.add(pinned)
            ids.append(pinned)
    runs = db.scalars(
        select(JuniorAgentRun.thread_id).where(
            JuniorAgentRun.user_id == user.id,
            JuniorAgentRun.project_slug == project.slug,
            JuniorAgentRun.thread_id.is_not(None),
        )
    )
    for thread_id in runs:
        if thread_id is not None and thread_id not in seen:
            seen.add(thread_id)
            ids.append(thread_id)
    return ids


def get_project(db: Session, user: User, slug: str) -> JuniorProject:
    row = db.scalar(
        select(JuniorProject).where(JuniorProject.user_id == user.id, JuniorProject.slug == normalize_slug(slug))
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return row


def update_project(
    db: Session,
    user: User,
    slug: str,
    *,
    display_name: str | None = None,
    kind: str | None = None,
    repo_url: str | None = None,
    default_branch: str | None = None,
    notes: str | None = None,
    meta: dict[str, Any] | None = None,
) -> JuniorProject:
    row = get_project(db, user, slug)
    if display_name is not None:
        row.display_name = _clean_text(display_name, max_len=120)
    if kind is not None:
        row.kind = normalize_kind_project(kind)
    if repo_url is not None:
        row.repo_url = _clean_text(repo_url, max_len=400, required=False) or None
    if default_branch is not None:
        row.default_branch = _clean_text(default_branch, max_len=80, required=False) or "main"
    if notes is not None:
        row.notes = _clean_text(notes, max_len=4000, required=False) or None
    if meta is not None:
        row.meta = meta if isinstance(meta, dict) else {}
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return row


def upsert_project(
    db: Session,
    user: User,
    *,
    slug: str,
    display_name: str,
    kind: str | None,
    repo_url: str | None,
    default_branch: str | None,
    notes: str | None,
    meta: dict[str, Any] | None,
) -> JuniorProject:
    slug_value = normalize_slug(slug)
    name = _clean_text(display_name, max_len=120)
    kind_value = normalize_kind_project(kind)
    branch = _clean_text(default_branch or "main", max_len=80, required=False) or "main"
    note = _clean_text(notes, max_len=4000, required=False) or None
    url = _clean_text(repo_url, max_len=400, required=False) or None
    payload = meta if isinstance(meta, dict) else {}
    now = datetime.now(timezone.utc)
    row = db.scalar(
        select(JuniorProject).where(JuniorProject.user_id == user.id, JuniorProject.slug == slug_value)
    )
    if row is None:
        row = JuniorProject(
            user_id=user.id,
            slug=slug_value,
            display_name=name,
            kind=kind_value,
            repo_url=url,
            default_branch=branch,
            notes=note,
            meta=payload,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.display_name = name
        row.kind = kind_value
        row.repo_url = url
        row.default_branch = branch
        row.notes = note
        row.meta = payload
        row.updated_at = now
    db.flush()
    return row


def _thread_for_project(db: Session, user: User, thread_id: UUID | None) -> JuniorThread | None:
    if thread_id is not None:
        return thread_owned(db, user, thread_id)
    return last_open_thread(db, user)


def launch_hint(project: JuniorProject) -> str:
    repo = (project.repo_url or "").strip() or "(no repo yet — placeholder project)"
    return (
        f"Start a Cursor agent on {project.slug} ({project.display_name}) at {repo} "
        f"branch {project.default_branch}. Use this agent-context pack (project + thread + "
        f"memories + search), not StoryKeep-only prompt text. Phone venue=phone is the same API. "
        f"Do not call an external Cursor API from this stub unless already wired; this slice "
        f"records status=context_ready."
    )


def build_agent_context(
    db: Session,
    user: User,
    *,
    project_slug: str,
    query: str | None = None,
    thread_id: UUID | None = None,
) -> dict[str, Any]:
    project = get_project(db, user, project_slug)
    thread = _thread_for_project(db, user, thread_id)
    recent: list[JuniorThreadMessage] = []
    thread_summary = None
    if thread is not None:
        recent = recent_thread_context(db, thread)
        thread_summary = (thread.summary or thread.title or "").strip() or None
    memories = top_memories(db, user)
    hits: list[dict[str, Any]] = []
    q = (query or "").strip()
    if q:
        try:
            hits = search(db, user, q, limit=8)
        except HTTPException:
            hits = []
    return {
        "project": project,
        "thread": thread,
        "thread_summary": thread_summary,
        "recent_messages": recent,
        "memories": memories,
        "search_hits": hits,
        "launch_hint": launch_hint(project),
    }


def update_agent_context(
    db: Session,
    user: User,
    slug: str,
    *,
    query: str | None = None,
    thread_id: UUID | None = None,
    set_query: bool = False,
    set_thread_id: bool = False,
) -> dict[str, Any]:
    project = get_project(db, user, slug)
    meta = dict(project.meta or {})
    if set_query:
        cleaned = (query or "").strip()[:200]
        if cleaned:
            meta["context_q"] = cleaned
        else:
            meta.pop("context_q", None)
    if set_thread_id:
        if thread_id is not None:
            thread_owned(db, user, thread_id)
            meta["context_thread_id"] = str(thread_id)
        else:
            meta.pop("context_thread_id", None)
    project.meta = meta
    project.updated_at = datetime.now(timezone.utc)
    db.flush()
    stored_q = str(meta.get("context_q") or "").strip() or None
    stored_thread = _as_uuid(meta.get("context_thread_id"))
    return build_agent_context(
        db, user, project_slug=slug, query=stored_q, thread_id=stored_thread
    )


def project_agent_context(
    db: Session,
    user: User,
    slug: str,
    *,
    query: str | None = None,
) -> dict[str, Any]:
    get_project(db, user, slug)
    return build_agent_context(db, user, project_slug=slug, query=query)


def update_project_agent_context(
    db: Session,
    user: User,
    slug: str,
    *,
    query: str | None = None,
    thread_id: UUID | None = None,
    set_query: bool = False,
    set_thread_id: bool = False,
) -> dict[str, Any]:
    get_project(db, user, slug)
    return update_agent_context(
        db,
        user,
        slug,
        query=query,
        thread_id=thread_id,
        set_query=set_query,
        set_thread_id=set_thread_id,
    )


def thread_agent_context(
    db: Session,
    user: User,
    thread_id: UUID,
    slug: str,
    *,
    query: str | None = None,
) -> dict[str, Any]:
    thread_owned(db, user, thread_id)
    return build_agent_context(
        db, user, project_slug=slug, query=query, thread_id=thread_id
    )


def update_thread_agent_context(
    db: Session,
    user: User,
    thread_id: UUID,
    slug: str,
    *,
    query: str | None = None,
    thread_id_value: UUID | None = None,
    set_query: bool = False,
    set_thread_id: bool = False,
) -> dict[str, Any]:
    thread_owned(db, user, thread_id)
    if set_thread_id and thread_id_value is not None and thread_id_value != thread_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent context not found")
    return update_agent_context(
        db,
        user,
        slug,
        query=query,
        thread_id=thread_id,
        set_query=set_query,
        set_thread_id=True,
    )


def project_agent_owned(db: Session, user: User, slug: str, run_id: UUID) -> JuniorAgentRun:
    project = get_project(db, user, slug)
    row = agent_run_owned(db, user, run_id)
    if row.project_slug != project.slug:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    return row


def thread_agent_owned(db: Session, user: User, thread_id: UUID, run_id: UUID) -> JuniorAgentRun:
    thread_owned(db, user, thread_id)
    row = agent_run_owned(db, user, run_id)
    if row.thread_id != thread_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    return row


def agent_run_owned(db: Session, user: User, run_id: UUID) -> JuniorAgentRun:
    row = db.get(JuniorAgentRun, run_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    return row


def normalize_agent_status(value: str | None) -> str:
    token = (value or "").strip().lower()
    if token not in AGENT_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid agent status")
    return token


def update_agent_run(
    db: Session,
    user: User,
    run_id: UUID,
    *,
    prompt: str | None = None,
    status_value: str | None = None,
    cursor_agent_id: str | None = None,
    thread_id: UUID | None = None,
    meta: dict[str, Any] | None = None,
    set_status: bool = False,
    set_cursor_agent_id: bool = False,
    set_thread_id: bool = False,
    set_meta: bool = False,
) -> JuniorAgentRun:
    row = agent_run_owned(db, user, run_id)
    if prompt is not None:
        row.prompt = _clean_text(prompt, max_len=CONTENT_MAX)
    if set_status:
        row.status = normalize_agent_status(status_value)
    if set_cursor_agent_id:
        cleaned = (cursor_agent_id or "").strip()
        row.cursor_agent_id = cleaned or None
    if set_thread_id:
        if thread_id is not None:
            thread_owned(db, user, thread_id)
        row.thread_id = thread_id
    if set_meta and meta is not None:
        row.meta = meta
    db.flush()
    return row


def update_project_agent(
    db: Session,
    user: User,
    slug: str,
    run_id: UUID,
    *,
    prompt: str | None = None,
    status_value: str | None = None,
    cursor_agent_id: str | None = None,
    thread_id: UUID | None = None,
    meta: dict[str, Any] | None = None,
    set_status: bool = False,
    set_cursor_agent_id: bool = False,
    set_thread_id: bool = False,
    set_meta: bool = False,
) -> JuniorAgentRun:
    project_agent_owned(db, user, slug, run_id)
    return update_agent_run(
        db,
        user,
        run_id,
        prompt=prompt,
        status_value=status_value,
        cursor_agent_id=cursor_agent_id,
        thread_id=thread_id,
        meta=meta,
        set_status=set_status,
        set_cursor_agent_id=set_cursor_agent_id,
        set_thread_id=set_thread_id,
        set_meta=set_meta,
    )


def update_thread_agent(
    db: Session,
    user: User,
    thread_id: UUID,
    run_id: UUID,
    *,
    prompt: str | None = None,
    status_value: str | None = None,
    cursor_agent_id: str | None = None,
    thread_id_value: UUID | None = None,
    meta: dict[str, Any] | None = None,
    set_status: bool = False,
    set_cursor_agent_id: bool = False,
    set_thread_id: bool = False,
    set_meta: bool = False,
) -> JuniorAgentRun:
    thread_agent_owned(db, user, thread_id, run_id)
    return update_agent_run(
        db,
        user,
        run_id,
        prompt=prompt,
        status_value=status_value,
        cursor_agent_id=cursor_agent_id,
        thread_id=thread_id_value,
        meta=meta,
        set_status=set_status,
        set_cursor_agent_id=set_cursor_agent_id,
        set_thread_id=set_thread_id,
        set_meta=set_meta,
    )


def list_agent_runs(db: Session, user: User) -> list[JuniorAgentRun]:
    rows, _ = list_agent_runs_page(db, user, limit=PAGE_MAX)
    return rows


def list_agent_runs_page(
    db: Session,
    user: User,
    *,
    limit: int | None = PAGE_DEFAULT,
    cursor: UUID | str | None = None,
    before_id: UUID | str | None = None,
    project_slug: str | None = None,
    thread_id: UUID | str | None = None,
) -> tuple[list[JuniorAgentRun], str | None]:
    cap = clamp_page_limit(limit)
    stmt = select(JuniorAgentRun).where(JuniorAgentRun.user_id == user.id)
    slug = (project_slug or "").strip().lower()
    if slug:
        stmt = stmt.where(JuniorAgentRun.project_slug == normalize_slug(slug))
    thread_filter = _as_uuid(thread_id) if thread_id is not None else None
    if thread_filter is not None:
        stmt = stmt.where(JuniorAgentRun.thread_id == thread_filter)
    marker = _as_uuid(before_id) or _as_uuid(cursor)
    if marker is not None:
        ref = db.scalar(
            select(JuniorAgentRun).where(
                JuniorAgentRun.user_id == user.id, JuniorAgentRun.id == marker
            )
        )
        if ref is not None:
            stmt = stmt.where(
                or_(
                    JuniorAgentRun.created_at < ref.created_at,
                    and_(
                        JuniorAgentRun.created_at == ref.created_at,
                        JuniorAgentRun.id < ref.id,
                    ),
                )
            )
    stmt = stmt.order_by(JuniorAgentRun.created_at.desc(), JuniorAgentRun.id.desc()).limit(cap + 1)
    rows = list(db.scalars(stmt))
    has_more = len(rows) > cap
    page = rows[:cap]
    next_cursor = str(page[-1].id) if has_more and page else None
    return page, next_cursor


def record_agent_run(
    db: Session,
    user: User,
    *,
    project_slug: str,
    prompt: str,
    thread_id: UUID | None,
    query: str | None = None,
) -> tuple[JuniorAgentRun, dict[str, Any]]:
    body = _clean_text(prompt, max_len=CONTENT_MAX)
    pack = build_agent_context(db, user, project_slug=project_slug, query=query or body, thread_id=thread_id)
    thread = pack["thread"]
    run = JuniorAgentRun(
        user_id=user.id,
        project_slug=pack["project"].slug,
        prompt=body,
        status="context_ready",
        cursor_agent_id=None,
        thread_id=thread.id if thread is not None else None,
        meta={"launch_hint": pack["launch_hint"], "called_cursor_api": False},
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    return run, pack


def seed_owner_projects_and_decisions(db: Session) -> None:
    from app.services.demo_lock import is_locked

    user = db.scalar(select(User).where(func.lower(User.email) == OWNER_EMAIL))
    if user is None or is_locked(user):
        return
    for item in SEED_PROJECTS:
        existing = db.scalar(
            select(JuniorProject).where(JuniorProject.user_id == user.id, JuniorProject.slug == item["slug"])
        )
        wanted = (item.get("repo_url") or "") or ""
        have = (getattr(existing, "repo_url", None) or "") if existing is not None else ""
        refresh_phone = item["slug"] == "junior-phone"
        if existing is None or (wanted and have != wanted) or refresh_phone:
            upsert_project(
                db,
                user,
                slug=item["slug"],
                display_name=item["display_name"],
                kind=item["kind"],
                repo_url=item["repo_url"],
                default_branch=item["default_branch"],
                notes=item["notes"],
                meta=item["meta"],
            )
    for content in SEED_DECISIONS:
        found = db.scalar(
            select(JuniorMemoryFact).where(
                JuniorMemoryFact.user_id == user.id,
                JuniorMemoryFact.kind == "decision",
                JuniorMemoryFact.content == content,
            )
        )
        if found is None:
            upsert_memory(db, user, memory_id=None, kind="decision", content=content, source_thread=None)
