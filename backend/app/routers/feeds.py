from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal, get_db
from app.deps import get_current_user
from app.models import Article, Category, Feed, User
from app.services import rss_shelves as rss_shelf_service
from app.presenters import feed_out
from app.schemas import DiscoverOut, FeedCandidate, FeedCreate, FeedDeleteIn, FeedOut, FeedUpdate, OpmlImportOut
from app.services import changelog, rss
from app.services import feed_delete
from app.services import opml as opml_service

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
    shelf_id: UUID | None = None,
    category_id: UUID | None = None,
    active: bool | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[FeedOut]:
    rss_shelf_service.ensure_user_shelves(db, user)
    stmt = select(Feed).where(Feed.user_id == user.id).order_by(Feed.title.asc().nulls_last())
    if shelf_id:
        stmt = stmt.where(Feed.shelf_id == shelf_id)
    if category_id:
        stmt = stmt.where(Feed.category_id == category_id)
    if active is not None:
        stmt = stmt.where(Feed.is_active.is_(active))
    feeds = db.scalars(stmt).all()
    return [feed_out(feed, *_counts(db, feed.id)) for feed in feeds]


def _subscribe(
    db: Session,
    user: User,
    url: str,
    *,
    title: str | None = None,
    shelf_id: UUID | None = None,
    category_id: UUID | None = None,
    background: BackgroundTasks | None = None,
) -> tuple[Feed, bool]:
    rss_shelf_service.ensure_user_shelves(db, user)
    existing = db.scalar(select(Feed).where(Feed.user_id == user.id, Feed.url == url))
    if existing:
        return existing, False
    shelf = rss_shelf_service.shelf_by_id(db, user, shelf_id) if shelf_id else rss_shelf_service.inbox_shelf(db, user)
    if not shelf:
        raise HTTPException(status_code=404, detail="Shelf not found")
    if category_id:
        try:
            rss_shelf_service.validate_category_on_shelf(db, user, shelf.id, category_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    else:
        category_id = rss_shelf_service.uncategorized_category(db, shelf).id
    feed = Feed(user_id=user.id, url=url, title=title or url, shelf_id=shelf.id, category_id=category_id)
    db.add(feed)
    db.flush()
    changelog.record(db, user.id, "feed", feed.id, "upsert", {"url": url})
    try:
        rss.refresh_feed(db, feed, extract=False)
    except Exception as exc:
        feed.last_error = str(exc)[:500]
        db.add(feed)
        db.commit()
    if background is not None:
        background.add_task(_refresh_later, feed.id)
    db.refresh(feed)
    return feed, True


@router.get("/feeds/opml")
def export_opml(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    feeds = [
        feed
        for feed in db.scalars(select(Feed).where(Feed.user_id == user.id).order_by(Feed.title.asc().nulls_last())).all()
        if feed.url != "https://storykeep.local/saved-pages"
    ]
    xml = opml_service.build_opml(feeds)
    return Response(
        content=xml,
        media_type="text/xml; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="storykeep.opml"'},
    )


@router.post("/feeds/import-opml", response_model=OpmlImportOut)
async def import_opml(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OpmlImportOut:
    raw = (await file.read()).decode("utf-8", errors="replace")
    try:
        outlines = opml_service.parse_opml(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    imported = 0
    skipped = 0
    errors: list[dict[str, str]] = []
    for outline in outlines:
        url = outline.get("url") or ""
        try:
            _, created = _subscribe(db, user, url, title=outline.get("title"), background=background)
        except Exception as exc:
            errors.append({"url": url, "detail": str(exc)[:300]})
            continue
        if created:
            imported += 1
        else:
            skipped += 1
    return OpmlImportOut(imported=imported, skipped=skipped, errors=errors)


@router.get("/feeds/discover", response_model=DiscoverOut)
def discover_feeds(
    url: str = Query(min_length=3),
    user: User = Depends(get_current_user),
) -> DiscoverOut:
    _ = user
    try:
        candidates = rss.discover_feeds(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DiscoverOut(
        queried_url=url,
        candidates=[FeedCandidate(**row) for row in candidates],
    )


@router.post("/feeds", response_model=FeedOut, status_code=201)
def create_feed(
    payload: FeedCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FeedOut:
    url = str(payload.url)
    feed, created = _subscribe(
        db,
        user,
        url,
        title=payload.title,
        shelf_id=payload.shelf_id,
        category_id=payload.category_id,
        background=background,
    )
    if not created:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Feed already added")
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
    if "shelf_id" in data and data["shelf_id"]:
        if not rss_shelf_service.shelf_by_id(db, user, data["shelf_id"]):
            raise HTTPException(status_code=404, detail="Shelf not found")
    if "category_id" in data and data["category_id"]:
        target_shelf = data.get("shelf_id") or feed.shelf_id
        if not target_shelf:
            raise HTTPException(status_code=400, detail="Feed has no shelf")
        try:
            rss_shelf_service.validate_category_on_shelf(db, user, target_shelf, data["category_id"])
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if "shelf_id" in data and data["shelf_id"] and data["shelf_id"] != feed.shelf_id:
            feed.shelf_id = data["shelf_id"]
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
    return feed_delete.remove_feed(db, user, feed_id, force=force)


@router.post("/feeds/{feed_id}")
def delete_feed_post(
    feed_id: UUID,
    payload: FeedDeleteIn | None = None,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    body_force = bool(payload.force) if payload else False
    return feed_delete.remove_feed(db, user, feed_id, force=force or body_force)


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
