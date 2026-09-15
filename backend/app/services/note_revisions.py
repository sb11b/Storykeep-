from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, NoteRevision, OverlayAddition, User
from app.services.destination import is_composed_guid

REVISION_KEEP = 20
REVISION_DAYS = 30
SHRINK_RATIO = 0.2


class NoteShrinkBlocked(Exception):
    def __init__(self, current_chars: int, incoming_chars: int):
        self.current_chars = current_chars
        self.incoming_chars = incoming_chars
        super().__init__(shrink_confirm_message(current_chars, incoming_chars))


def shrink_confirm_message(current_chars: int, incoming_chars: int) -> str:
    return f"This save is much shorter ({incoming_chars} vs {current_chars}). Save anyway?"


def stored_note_markdown(article: Article, db: Session, user: User) -> str:
    body = (article.content_text or "").strip()
    if body:
        return body
    addition = db.scalar(
        select(OverlayAddition)
        .where(OverlayAddition.user_id == user.id, OverlayAddition.article_id == article.id)
        .order_by(OverlayAddition.created_at.asc())
    )
    return (addition.markdown if addition else "") or ""


def char_count(markdown: str) -> int:
    return len(markdown or "")


def is_severe_shrink(current_chars: int, incoming_chars: int) -> bool:
    if current_chars < 40:
        return False
    return incoming_chars < current_chars * SHRINK_RATIO


def require_composed_owner(article: Article) -> None:
    if not is_composed_guid(article.guid):
        raise HTTPException(status_code=400, detail="Imported vault notes stay read-only.")


def snapshot_before_save(
    db: Session,
    user: User,
    article: Article,
    incoming_markdown: str,
    *,
    confirm_short: bool = False,
) -> NoteRevision | None:
    """Insert a revision of the current body. Raises NoteShrinkBlocked when the save is tiny."""
    require_composed_owner(article)
    current = stored_note_markdown(article, db, user)
    incoming = incoming_markdown or ""
    if current == incoming:
        return None
    current_n = char_count(current)
    incoming_n = char_count(incoming)
    if not confirm_short and is_severe_shrink(current_n, incoming_n):
        raise NoteShrinkBlocked(current_n, incoming_n)
    if not current:
        return None
    row = NoteRevision(
        user_id=user.id,
        article_id=article.id,
        markdown=current,
        char_count=current_n,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    prune_revisions(db, user, article.id)
    return row


def prune_revisions(db: Session, user: User, article_id) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=REVISION_DAYS)
    stale = db.scalars(
        select(NoteRevision).where(
            NoteRevision.user_id == user.id,
            NoteRevision.article_id == article_id,
            NoteRevision.created_at < cutoff,
        )
    ).all()
    for row in stale:
        db.delete(row)
    kept = list(
        db.scalars(
            select(NoteRevision)
            .where(NoteRevision.user_id == user.id, NoteRevision.article_id == article_id)
            .order_by(NoteRevision.created_at.desc())
        ).all()
    )
    for row in kept[REVISION_KEEP:]:
        db.delete(row)
    db.flush()


def list_revisions(db: Session, user: User, article: Article) -> list[NoteRevision]:
    require_composed_owner(article)
    return list(
        db.scalars(
            select(NoteRevision)
            .where(NoteRevision.user_id == user.id, NoteRevision.article_id == article.id)
            .order_by(NoteRevision.created_at.desc())
        ).all()
    )


def owned_revision(db: Session, user: User, article: Article, revision_id) -> NoteRevision:
    require_composed_owner(article)
    row = db.scalar(
        select(NoteRevision).where(
            NoteRevision.id == revision_id,
            NoteRevision.user_id == user.id,
            NoteRevision.article_id == article.id,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="That revision was not found.")
    return row


def latest_revision(db: Session, user: User, article: Article) -> NoteRevision | None:
    require_composed_owner(article)
    return db.scalar(
        select(NoteRevision)
        .where(NoteRevision.user_id == user.id, NoteRevision.article_id == article.id)
        .order_by(NoteRevision.created_at.desc())
        .limit(1)
    )
