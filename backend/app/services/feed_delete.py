from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, delete, func, not_, or_, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.models import Article, Feed, User
from app.services import changelog

SAVED_CONFLICT = "This feed has saved articles. Retry with force=true to delete them."


def keeper_clause() -> ColumnElement[bool]:
    """Saved, starred, or filed-on-a-shelf copies survive feed removal."""
    return or_(
        Article.is_saved.is_(True),
        Article.is_starred.is_(True),
        Article.destination.isnot(None),
        Article.folder_id.isnot(None),
    )


def kept_article_count(db: Session, feed_id: UUID) -> int:
    return (
        db.scalar(select(func.count()).select_from(Article).where(Article.feed_id == feed_id, keeper_clause()))
        or 0
    )


def owned_feed(db: Session, user: User, feed_id: UUID) -> Feed:
    feed = db.get(Feed, feed_id)
    if not feed or feed.user_id != user.id:
        raise HTTPException(status_code=404, detail="Feed not found")
    return feed


def remove_feed(db: Session, user: User, feed_id: UUID, *, force: bool = False) -> dict[str, bool]:
    feed = owned_feed(db, user, feed_id)
    kept = kept_article_count(db, feed.id)
    if kept and not force:
        raise HTTPException(status_code=409, detail=SAVED_CONFLICT)
    db.execute(delete(Article).where(and_(Article.feed_id == feed.id, not_(keeper_clause()))))
    db.execute(update(Article).where(Article.feed_id == feed.id).values(feed_id=None))
    changelog.record(db, user.id, "feed", feed.id, "delete", {"url": feed.url, "force": force, "kept": kept})
    db.execute(delete(Feed).where(Feed.id == feed.id, Feed.user_id == user.id))
    db.commit()
    return {"ok": True}
