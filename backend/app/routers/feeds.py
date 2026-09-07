from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.deps import get_current_user
from app.models import Article, Category, Feed, User
from app.presenters import feed_out
from app.schemas import FeedCreate, FeedOut, FeedUpdate
from app.services import changelog, rss

router = APIRouter(tags=["feeds"])


def _counts(db: Session, feed_id: UUID) -> tuple[int, int, int]:
    total = db.scalar(select(func.count()).select_from(Article).where(Article.feed_id == feed_id)) or 0
    unread = (
        db.scalar(
            select(func.count()).select_from(Article).where(Article.feed_id == feed_id, Article.is_read.is_(False))
        )
        or 0
    )
    saved = (
        db.scalar(
            select(func.count()).select_from(Article).where(Article.feed_id == feed_id, Article.is_saved.is_(True))
        )
        or 0
    )
    return unread, saved, total


def _refresh_later(feed_id: UUID) -> None:
    db = SessionLocal()
    try:
        feed = db.get(Feed, feed_id)
        if feed:
            rss.refresh_feed(db, feed, extract=settings.extract_on_import)
    finally:
        db.close()


@router.get("/feeds", response_model=list[FeedOut])
def list_feeds(
    category_id: UUID | None = None,
    active: bool | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FeedOut]:
    stmt = select(Feed).where(Feed.user_id == user.id).order_by(Feed.title.asc().nulls_last())
    if category_id:
        stmt = stmt.where(Feed.category_id == category_id)
    if active is not None:
        stmt = stmt.where(Feed.is_active.is_(active))
    feeds = db.scalars(stmt).all()
    return [feed_out(feed, *_counts(db, feed.id)) for feed in feeds]


@router.post("/feeds", response_model=FeedOut, status_code=201)
def create_feed(
    payload: FeedCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FeedOut:
    url = str(payload.url)
    existing = db.scalar(select(Feed).where(Feed.user_id == user.id, Feed.url == url))
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Feed already added")
    if payload.category_id:
        category = db.get(Category, payload.category_id)
        if not category or category.user_id != user.id:
            raise HTTPException(status_code=404, detail="Category not found")
    feed = Feed(user_id=user.id, url=url, title=url, category_id=payload.category_id)
    db.add(feed)
    db.flush()
    changelog.record(db, user.id, "feed", feed.id, "upsert", {"url": url})
    try:
        rss.refresh_feed(db, feed, extract=False)
    except Exception as exc:
        feed.last_error = str(exc)[:500]
        db.add(feed)
        db.commit()
    background.add_task(_refresh_later, feed.id)
    db.refresh(feed)
    return feed_out(feed, *_counts(db, feed.id))


@router.get("/feeds/{feed_id}", response_model=FeedOut)
def get_feed(feed_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> FeedOut:
    feed = db.get(Feed, feed_id)
    if not feed or feed.user_id != user.id:
        raise HTTPException(status_code=404, detail="Feed not found")
    return feed_out(feed, *_counts(db, feed.id))


@router.patch("/feeds/{feed_id}", response_model=FeedOut)
def update_feed(
    feed_id: UUID,
    payload: FeedUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FeedOut:
    feed = db.get(Feed, feed_id)
    if not feed or feed.user_id != user.id:
        raise HTTPException(status_code=404, detail="Feed not found")
    data = payload.model_dump(exclude_unset=True)
    if "category_id" in data and data["category_id"]:
        category = db.get(Category, data["category_id"])
        if not category or category.user_id != user.id:
            raise HTTPException(status_code=404, detail="Category not found")
    for key, value in data.items():
        setattr(feed, key, value)
    changelog.record(db, user.id, "feed", feed.id, "upsert", data)
    db.add(feed)
    db.commit()
    db.refresh(feed)
    return feed_out(feed, *_counts(db, feed.id))


@router.delete("/feeds/{feed_id}")
def delete_feed(
    feed_id: UUID,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    feed = db.get(Feed, feed_id)
    if not feed or feed.user_id != user.id:
        raise HTTPException(status_code=404, detail="Feed not found")
    saved = (
        db.scalar(select(func.count()).select_from(Article).where(Article.feed_id == feed.id, Article.is_saved.is_(True)))
        or 0
    )
    if saved and not force:
        raise HTTPException(
            status_code=409,
            detail=f"This feed has {saved} saved articles. Retry with force=true to delete them.",
        )
    changelog.record(db, user.id, "feed", feed.id, "delete", {"url": feed.url})
    db.delete(feed)
    db.commit()
    return {"ok": True}


@router.post("/feeds/{feed_id}/mark-read")
def mark_feed_read(
    feed_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, int]:
    feed = db.get(Feed, feed_id)
    if not feed or feed.user_id != user.id:
        raise HTTPException(status_code=404, detail="Feed not found")
    now = datetime.now(timezone.utc)
    unread = db.scalars(select(Article).where(Article.feed_id == feed.id, Article.is_read.is_(False))).all()
    for article in unread:
        article.is_read = True
        article.read_at = now
        db.add(article)
    changelog.record(db, user.id, "feed", feed.id, "upsert", {"mark_read": len(unread)})
    db.commit()
    return {"updated": len(unread)}


@router.post("/feeds/{feed_id}/refresh", response_model=FeedOut)
def refresh_one(
    feed_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FeedOut:
    feed = db.get(Feed, feed_id)
    if not feed or feed.user_id != user.id:
        raise HTTPException(status_code=404, detail="Feed not found")
    rss.refresh_feed(db, feed, extract=settings.extract_on_import)
    db.refresh(feed)
    return feed_out(feed, *_counts(db, feed.id))


@router.post("/feeds/refresh")
def refresh_all(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int]:
    created = rss.refresh_user_feeds(db, user.id, extract=settings.extract_on_import)
    return {"created": created}
