from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Annotation, OverlayAddition, User
from app.presenters import annotation_out
from app.schemas import AnnotationOut


def collect_note_items(db: Session, user: User) -> list[AnnotationOut]:
    """Rows shown in the Notes rail: margin notes, highlights, and overlay additions."""
    notes = db.scalars(
        select(Annotation)
        .where(Annotation.user_id == user.id)
        .options(selectinload(Annotation.article))
    ).all()
    items = [annotation_out(note, note.article.title if note.article else None) for note in notes]
    additions = db.scalars(
        select(OverlayAddition)
        .where(OverlayAddition.user_id == user.id, OverlayAddition.article_id.isnot(None))
        .options(selectinload(OverlayAddition.article))
    ).all()
    for row in additions:
        article = row.article
        items.append(
            AnnotationOut(
                id=row.id,
                article_id=row.article_id,
                body=row.markdown,
                quote=row.title,
                kind="addition",
                created_at=row.created_at,
                updated_at=row.updated_at,
                article_title=(article.title if article else None) or row.title,
            )
        )
    items.sort(key=lambda item: item.updated_at, reverse=True)
    return items


def notes_feed_page(db: Session, user: User, limit: int, offset: int) -> tuple[list[AnnotationOut], int]:
    items = collect_note_items(db, user)
    return paginate_notes(items, limit, offset)


def paginate_notes(items: list[AnnotationOut], limit: int, offset: int) -> tuple[list[AnnotationOut], int]:
    return items[offset : offset + limit], len(items)


def notes_feed_total(db: Session, user: User) -> int:
    annotations = db.scalar(select(func.count()).select_from(Annotation).where(Annotation.user_id == user.id)) or 0
    additions = (
        db.scalar(
            select(func.count()).select_from(OverlayAddition).where(
                OverlayAddition.user_id == user.id, OverlayAddition.article_id.isnot(None)
            )
        )
        or 0
    )
    return int(annotations) + int(additions)
