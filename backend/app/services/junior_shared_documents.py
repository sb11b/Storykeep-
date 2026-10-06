"""Document storage for the Junior shared-memory API.

Documents are user-scoped text blobs (e.g. the junior-ledger) that can be
upserted, listed, and injected into Junior's prompt context.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import JuniorDocument, User

from app.services.junior_shared_memory import (
    PAGE_DEFAULT,
    _as_uuid,
    clamp_page_limit,
    normalize_slug,
)

# Maximum characters to inject from the junior-ledger document text.
_LEDGER_CAP = 1_200


def _document_out(row: JuniorDocument) -> dict[str, Any]:
    return {
        "id": row.id,
        "slug": row.slug,
        "title": row.title,
        "text": row.text,
        "summary": row.summary,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def get_document(db: Session, user: User, slug: str) -> JuniorDocument:
    slug = normalize_slug(slug)
    row = db.scalar(
        select(JuniorDocument).where(JuniorDocument.user_id == user.id, JuniorDocument.slug == slug)
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return row


def document_owned(db: Session, user: User, slug: str) -> JuniorDocument:
    return get_document(db, user, slug)


def list_documents_page(
    db: Session,
    user: User,
    *,
    limit: int = PAGE_DEFAULT,
    cursor: str | None = None,
    before_id: Any | None = None,
) -> tuple[list[JuniorDocument], str | None]:
    cap = clamp_page_limit(limit)
    stmt = select(JuniorDocument).where(JuniorDocument.user_id == user.id)
    marker = _as_uuid(before_id) or _as_uuid(cursor)
    if marker is not None:
        ref = db.scalar(
            select(JuniorDocument).where(
                JuniorDocument.user_id == user.id, JuniorDocument.id == marker
            )
        )
        if ref is not None:
            stmt = stmt.where(
                or_(
                    JuniorDocument.created_at < ref.created_at,
                    and_(
                        JuniorDocument.created_at == ref.created_at,
                        JuniorDocument.id < ref.id,
                    ),
                )
            )
    stmt = stmt.order_by(JuniorDocument.created_at.desc(), JuniorDocument.id.desc()).limit(cap + 1)
    rows = list(db.scalars(stmt))
    has_more = len(rows) > cap
    page = rows[:cap]
    next_cursor = str(page[-1].id) if has_more and page else None
    return page, next_cursor


def upsert_document(
    db: Session,
    user: User,
    slug: str,
    title: str,
    text: str | None = None,
    summary: str | None = None,
    *,
    set_text: bool = False,
    set_summary: bool = False,
) -> JuniorDocument:
    slug = normalize_slug(slug)
    existing = db.scalar(
        select(JuniorDocument).where(JuniorDocument.user_id == user.id, JuniorDocument.slug == slug)
    )
    if existing is None:
        row = JuniorDocument(user_id=user.id, slug=slug, title=title, text=text or "", summary=summary)
        db.add(row)
    else:
        row = existing
        row.title = title
        if set_text:
            row.text = text or ""
        if set_summary:
            row.summary = summary
        row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return row


def delete_document(db: Session, user: User, slug: str) -> None:
    slug = normalize_slug(slug)
    row = get_document(db, user, slug)
    db.delete(row)


def get_documents_for_prompt(
    db: Session, user: User, *, cap: int = 20
) -> list[dict[str, Any]]:
    """Return documents for injection into Junior's prompt context."""
    rows = db.scalars(
        select(JuniorDocument)
        .where(JuniorDocument.user_id == user.id)
        .order_by(JuniorDocument.created_at.desc())
        .limit(cap)
    ).all()
    return [_document_out(r) for r in rows]


def get_ledger_for_prompt(
    db: Session, user: User, *, cap: int = _LEDGER_CAP
) -> str | None:
    """Return the junior-ledger document text, capped.  None if missing."""
    row = db.scalar(
        select(JuniorDocument)
        .where(JuniorDocument.user_id == user.id, JuniorDocument.slug == "junior-ledger")
    )
    if row is None:
        return None
    text = (row.text or "").strip()
    if not text:
        return None
    return text[:cap] if len(text) > cap else text
