"""Include-slice resolution for chat turns.

Resolves article, note, and working-note context attachments into
excerpts and validates the combined payload size. Extracted from
chat_stream.py to keep the router thin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services import chat as chat_service
from app.services.destination import is_composed_guid
from app.services.include_chunk import WORKING_NOTE_CHAR_CAP
from app.services.include_chunk import format_excerpt as format_include_excerpt
from app.services.include_chunk import resolve_include_slice
from app.services.include_chunk import slice_meta as include_slice_meta
from app.services.working_note import heading_from_instruction

if TYPE_CHECKING:
    from app.models import User
    from app.routers.chat_stream import ChatIn


class IncludeResult:
    """Resolved include-slice context for a chat turn."""

    def __init__(self) -> None:
        self.excerpt: str | None = None
        self.note_excerpt: str | None = None
        self.article_body: str | None = None
        self.note_body: str | None = None
        self.working_excerpt: str | None = None
        self.include_meta: dict[str, object] = {}
        self.include_chars: int = 0
        self.system_overhead: int = 0
        self.has_attachments: bool = False
        self.history_for_xai: list[dict] = []


def resolve_includes(
    db: Session,
    user: "User",
    payload: "ChatIn",
    user_text: str,
    history: list[dict],
) -> IncludeResult:
    """Resolve article/note/working-note includes for a chat turn.

    Returns an IncludeResult with all excerpts, metadata, and size checks.
    Raises HTTPException on validation failures.
    """
    result = IncludeResult()

    def _owned_include_slice(article: Any, *, cap: int | None = None, hard_max: int | None = None):
        try:
            return resolve_include_slice(
                chat_service.article_body_text(article),
                mode=payload.include_mode,
                selection=payload.include_selection,
                heading=payload.include_heading,
                offset=payload.include_offset or 0,
                title=article.title,
                html=getattr(article, "content_html", None),
                cap=cap,
                hard_max=hard_max,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    from app.routers.articles import _owned_article

    include_article = bool(payload.include_article)
    include_note = bool(payload.include_note_id)

    if include_article:
        if not payload.article_id:
            raise HTTPException(status_code=400, detail="Open an article before attaching it to chat.")
        article = _owned_article(db, user, payload.article_id)
        owned_slice = _owned_include_slice(article)
        result.article_body = owned_slice.text
        result.excerpt = format_include_excerpt((article.title or "Untitled").strip(), owned_slice)
        result.excerpt = (
            f"article_id: {article.id}\n"
            f"Open in reader: [{(article.title or 'Untitled').strip()}](#article/{article.id})\n"
            f"{result.excerpt}"
        )
        result.include_meta = include_slice_meta(owned_slice)

    if include_note:
        if include_article and payload.article_id == payload.include_note_id:
            result.note_excerpt = result.excerpt
            result.note_body = result.article_body
        else:
            note = _owned_article(db, user, payload.include_note_id)
            note_slice = _owned_include_slice(note)
            result.note_body = note_slice.text
            result.note_excerpt = format_include_excerpt((note.title or "Untitled").strip(), note_slice)
            if not result.include_meta:
                result.include_meta = include_slice_meta(note_slice)

    if payload.working_note_id and chat_service.should_attach_working_note(user_text):
        working = _owned_article(db, user, payload.working_note_id)
        if not is_composed_guid(working.guid):
            raise HTTPException(status_code=400, detail="Work in Junior is for StoryKeep-authored notes.")
        work_mode = payload.include_mode
        work_heading = payload.include_heading
        if (not work_mode or work_mode == "auto") and not (work_heading or "").strip():
            guessed = heading_from_instruction(user_text, chat_service.article_body_text(working))
            if guessed:
                work_mode = "heading"
                work_heading = guessed
        try:
            working_slice = resolve_include_slice(
                chat_service.article_body_text(working),
                mode=work_mode,
                selection=payload.include_selection,
                heading=work_heading,
                offset=payload.include_offset or 0,
                title=working.title,
                html=getattr(working, "content_html", None),
                cap=WORKING_NOTE_CHAR_CAP,
                hard_max=WORKING_NOTE_CHAR_CAP,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        result.working_excerpt = format_include_excerpt((working.title or "Untitled").strip(), working_slice)
        result.working_excerpt = f"working_note_id: {working.id}\n{result.working_excerpt}"
        result.include_meta = include_slice_meta(working_slice)

    result.include_chars = len(result.article_body or "")
    if result.note_body and result.note_body != result.article_body:
        result.include_chars += len(result.note_body)

    rough_thread = chat_service.messages_for_xai(
        history,
        model=chat_service.CURRENT_CHAT_MODEL,
        db=db,
        user=user,
    )
    result.working_excerpt = chat_service.cap_working_excerpt(
        result.working_excerpt,
        thread_chars=chat_service.messages_char_count(rough_thread),
        include_chars=result.include_chars,
    )

    result.system_overhead = len(result.excerpt or "") + len(result.note_excerpt or "") + len(result.working_excerpt or "")

    prepared = chat_service.messages_for_xai(
        history,
        model=chat_service.CURRENT_CHAT_MODEL,
        db=db,
        user=user,
        trim_cap=chat_service.thread_trim_cap(system_overhead=result.system_overhead),
    )
    history_for_xai = chat_service.validate_payload(prepared)
    chat_service.reject_oversized_send(
        history,
        article_body=result.article_body,
        note_body=result.note_body,
        working_excerpt=result.working_excerpt,
        system_overhead=result.system_overhead,
    )

    result.has_attachments = any(item.get("files") for item in history)
    result.history_for_xai = history_for_xai

    return result
