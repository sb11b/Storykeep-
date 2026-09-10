from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, Correction, User
from app.services import changelog


def correction_for_article(db: Session, user: User, article_id: UUID) -> Correction | None:
    rows = db.scalars(
        select(Correction)
        .where(Correction.user_id == user.id, Correction.article_id == article_id)
        .order_by(Correction.created_at.asc())
    ).all()
    if not rows:
        return None
    primary = rows[-1]
    for extra in rows[:-1]:
        db.delete(extra)
    return primary


def upsert_correction(db: Session, user: User, article: Article, markdown: str) -> Correction:
    body = (markdown or "").strip()
    if not body:
        raise ValueError("Correction text is required.")
    row = correction_for_article(db, user, article.id)
    if row:
        row.markdown = body
    else:
        row = Correction(user_id=user.id, article_id=article.id, markdown=body)
        db.add(row)
        db.flush()
    changelog.record(db, user.id, "correction", row.id, "upsert", {"article_id": str(article.id)})
    db.commit()
    db.refresh(row)
    return row


def unlink_correction(db: Session, user: User, article_id: UUID) -> bool:
    rows = db.scalars(
        select(Correction).where(Correction.user_id == user.id, Correction.article_id == article_id)
    ).all()
    if not rows:
        return False
    for row in rows:
        changelog.record(db, user.id, "correction", row.id, "delete", {"article_id": str(article_id)})
        db.delete(row)
    db.commit()
    return True
