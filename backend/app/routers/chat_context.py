"""Owns the chat route's per-turn context gathering (unread news, mail, calendar, memory, chat index) extracted from chat_stream."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from app.services import calendar_access as calendars
from app.services import chat_index
from app.services import fastmail_jmap as jmap
from app.services import junior_memory
from app.services import mail as mail_service
from app.services import mail_tool
from app.services.demo_lock import is_locked
from app.services.junior_jobs import attach_unread_catalog, unread_news_block
from app.services import chat as chat_service


@dataclass
class ContextResult:
    """Per-turn context gathered for the model prompt."""

    history_for_xai: list
    unread_catalog: str | None
    calendar_connected: bool
    mail_connected: bool
    unread_mail_md: str | None
    memory_block: str | None
    chats_enabled: bool
    already_indexed: bool
    already_read: bool
    index_block: str | None
    read_meta: str | None
    read_slice_payload: dict[str, object] | None


def gather_context(
    db,
    user,
    *,
    user_id,
    user_text,
    mail_unread,
    history_for_xai,
    step,
) -> ContextResult:
    """Collect the per-turn context — unread news, mail, calendar, memory, and chat-index state — that feeds the model prompt."""
    step("unread")
    unread_catalog = None if mail_unread else unread_news_block(db, user.id, user_text)
    if unread_catalog:
        history_for_xai = chat_service.validate_payload(
            attach_unread_catalog(history_for_xai, unread_catalog)
        )
    step("calendar")
    calendar_connected = calendars.is_connected(db, user_id) and not is_locked(user)
    step("mail")
    mail_connected = mail_service.has_token(db, user)
    unread_mail_md = None
    if mail_unread:
        if mail_connected:
            try:
                listed = jmap.list_emails(
                    mail_service.require_token(db, user), role="inbox", unseen=True, limit=50
                )
                unread_mail_md = mail_tool.unread_mail_markdown(listed.get("items") or [])
            except Exception:
                unread_mail_md = "Fastmail unread list was unavailable this turn."
        else:
            unread_mail_md = "Fastmail mail is not connected. Open Mail in StoryKeep."
    step("memory")
    memory_block = junior_memory.system_section(db, user)
    chats_enabled = chat_index.can_use(user)
    already_indexed = False
    already_read = False
    read_slice_payload: dict[str, object] | None = None
    index_block: str | None = None
    read_meta: str | None = None
    if chats_enabled:
        if chat_index.wants_index(user_text):
            index_block = chat_index.format_index(chat_index.build_index(db, user))
            already_indexed = True
        elif chat_index.wants_read(user_text):
            chat_id = chat_index.extract_conversation_id(user_text)
            if chat_id:
                try:
                    read_slice_payload = chat_index.read_slice(db, user, chat_id)
                    already_read = True
                    read_meta = (
                        f"Opened Junior chat slice: {read_slice_payload.get('title')} · "
                        f"id={read_slice_payload.get('id')} · "
                        f"truncated={str(bool(read_slice_payload.get('truncated'))).lower()}."
                    )
                except HTTPException:
                    read_meta = "No chat with that id. Use the index. Do not invent a thread."
            else:
                read_meta = chat_index.NEED_ID_SYSTEM
    return ContextResult(
        history_for_xai=history_for_xai,
        unread_catalog=unread_catalog,
        calendar_connected=calendar_connected,
        mail_connected=mail_connected,
        unread_mail_md=unread_mail_md,
        memory_block=memory_block,
        chats_enabled=chats_enabled,
        already_indexed=already_indexed,
        already_read=already_read,
        index_block=index_block,
        read_meta=read_meta,
        read_slice_payload=read_slice_payload,
    )
