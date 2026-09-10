import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models import Annotation, Archive, Article, Feed, OverlayAddition, OverlayHighlight, Tag, User
from app.presenters import annotation_out, archive_out, article_list_item, article_out, tag_out
from app.services.destination import apply_shelf_filter
from app.schemas import (
    AnnotationIn,
    AnnotationOut,
    ArchiveCreate,
    ArchiveOut,
    ArticleBulkIn,
    ArticleListItem,
    ArticleOut,
    ArticlePatch,
    ExtractOut,
    MarkReadIn,
    Page,
    SaveUrlIn,
    TagIdsIn,
    TagIn,
    TagOut,
)
from app.services.overlay_search import article_search_match
from app.services import archive as archive_service, changelog, extractor
from app.services.extractor import ExtractFailedError, _feed_body_valid, _is_dek_only

router = APIRouter(tags=["articles"])

EXTRACT_MSG_SUCCESS = "Updated from the page."
EXTRACT_MSG_DEK_KEPT = "Page had no full article; kept the short feed text."
EXTRACT_MSG_FAILED = "Extract failed; previous text kept."


def _extract_user_message(
    prev_html: str | None,
    prev_text: str | None,
    next_html: str | None,
    next_text: str | None,
) -> tuple[bool, str]:
    had_previous = bool((prev_html or prev_text or "").strip())
    prev_usable = _feed_body_valid(prev_html, prev_text)
    next_usable = _feed_body_valid(next_html, next_text)
    next_dek = _is_dek_only(next_html, next_text)
    content_changed = (prev_html or "").strip() != (next_html or "").strip() or (prev_text or "").strip() != (
        next_text or ""
    ).strip()

    if next_usable and (not prev_usable or content_changed):
        return True, EXTRACT_MSG_SUCCESS
    if had_previous and next_dek:
        return True, EXTRACT_MSG_DEK_KEPT
    if had_previous:
        return False, EXTRACT_MSG_FAILED
    return False, EXTRACT_MSG_FAILED
logger = logging.getLogger(__name__)

SAVED_PAGES_URL = "https://storykeep.local/saved-pages"


def _saved_pages_feed(db: Session, user: User) -> Feed:
    feed = db.scalar(select(Feed).where(Feed.user_id == user.id, Feed.url == SAVED_PAGES_URL))
    if feed:
        return feed
    feed = Feed(
        user_id=user.id,
        url=SAVED_PAGES_URL,
        title="Saved pages",
        site_url=None,
        is_active=False,
    )
    db.add(feed)
    db.flush()
    changelog.record(db, user.id, "feed", feed.id, "upsert", {"url": SAVED_PAGES_URL})
    return feed


def _owned_article(db: Session, user: User, article_id: UUID) -> Article:
    article = db.scalar(
        select(Article)
        .join(Feed)
        .where(Article.id == article_id, Feed.user_id == user.id)
        .options(
            selectinload(Article.feed),
            selectinload(Article.tags),
            selectinload(Article.annotations),
            selectinload(Article.archives),
            selectinload(Article.overlay_highlights),
            selectinload(Article.overlay_additions),
            selectinload(Article.corrections),
        )
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


def _article_payload(db: Session, user: User, article_id: UUID) -> ArticleOut:
    article = _owned_article(db, user, article_id)
    children = db.scalars(
        select(Article).where(Article.parent_id == article.id).order_by(Article.updated_at.desc())
    ).all()
    return article_out(article, children)


@router.get("/articles", response_model=Page[ArticleListItem])
def list_articles(
    feed_id: UUID | None = None,
    category_id: UUID | None = None,
    tag_id: UUID | None = None,
    saved: bool | None = None,
    starred: bool | None = None,
    read: bool | None = None,
    q: str | None = None,
    shelf: str | None = Query(default=None),
    since: datetime | None = None,
    limit: int = Query(default=40, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: str = "published_desc",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[ArticleListItem]:
    stmt = (
        select(Article)
        .join(Feed)
        .where(Feed.user_id == user.id)
        .options(selectinload(Article.feed), selectinload(Article.tags))
    )
    if feed_id:
        stmt = stmt.where(Article.feed_id == feed_id)
    if category_id:
        stmt = stmt.where(Feed.category_id == category_id)
    if tag_id:
        stmt = stmt.join(Article.tags).where(Tag.id == tag_id, Tag.user_id == user.id)
    if saved is not None:
        stmt = stmt.where(Article.is_saved.is_(saved))
    if starred is not None:
        stmt = stmt.where(Article.is_starred.is_(starred))
    if read is not None:
        stmt = stmt.where(Article.is_read.is_(read))
    if since:
        stmt = stmt.where(Article.updated_at >= since)
    stmt = apply_shelf_filter(stmt, shelf)
    if q:
        tsquery = func.plainto_tsquery("english", q)
        stmt = stmt.where(article_search_match(user.id, tsquery, q))
    if sort == "published_asc":
        stmt = stmt.order_by(Article.published_at.asc().nulls_last(), Article.created_at.asc())
    elif sort == "saved_desc":
        stmt = stmt.order_by(Article.saved_at.desc().nulls_last(), Article.published_at.desc().nulls_last())
    else:
        stmt = stmt.order_by(Article.published_at.desc().nulls_last(), Article.created_at.desc())

    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.scalars(stmt.offset(offset).limit(limit)).unique().all()
    return Page(items=[article_list_item(article) for article in items], total=total, limit=limit, offset=offset)


@router.post("/articles/from-url", response_model=ArticleOut, status_code=201)
def save_url(
    payload: SaveUrlIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ArticleOut:
    url = str(payload.url)
    feed = _saved_pages_feed(db, user)
    existing = db.scalar(select(Article).where(Article.feed_id == feed.id, Article.guid == url[:2000]))
    now = datetime.now(timezone.utc)
    html, text, title, image = extractor.extract_page(url)
    usable = extractor._extract_usable(html, text)
    if existing:
        article = existing
        if usable:
            if html:
                article.content_html = html
            if text:
                article.content_text = text
            article.fetched_at = now
        if title:
            article.title = title[:500]
        if image:
            article.image_url = image
        article.is_saved = True
        article.saved_at = article.saved_at or now
    else:
        article = Article(
            feed_id=feed.id,
            guid=url[:2000],
            url=url[:4000],
            title=(title or url)[:500],
            content_html=html if usable else None,
            content_text=text if usable else None,
            image_url=image,
            published_at=now,
            fetched_at=now if usable and (html or text) else None,
            is_saved=True,
            saved_at=now,
            source_kind="url",
            source_ref=url[:4000],
        )
        db.add(article)
        db.flush()
    archive_service.snapshot_article(db, article, "html")
    changelog.record(db, user.id, "article", article.id, "upsert", {"url": url, "saved_page": True})
    db.commit()
    return article_out(_owned_article(db, user, article.id))


@router.get("/articles/{article_id}", response_model=ArticleOut)
def get_article(article_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> ArticleOut:
    article = _owned_article(db, user, article_id)
    if extractor.article_needs_page_extract(article):
        try:
            extractor.fill_article(db, article, force=False)
            db.commit()
            db.refresh(article)
        except ExtractFailedError:
            db.rollback()
            article = _owned_article(db, user, article_id)
        except Exception as exc:
            logger.warning("auto extract failed for article %s: %s", article.id, exc)
            db.rollback()
            article = _owned_article(db, user, article_id)
    children = db.scalars(
        select(Article).where(Article.parent_id == article.id).order_by(Article.updated_at.desc())
    ).all()
    return article_out(article, children)


@router.patch("/articles/{article_id}", response_model=ArticleOut)
def patch_article(
    article_id: UUID,
    payload: ArticlePatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ArticleOut:
    article = _owned_article(db, user, article_id)
    now = datetime.now(timezone.utc)
    if payload.is_read is not None:
        article.is_read = payload.is_read
        article.read_at = now if payload.is_read else None
    if payload.is_starred is not None:
        article.is_starred = payload.is_starred
    if payload.is_saved is not None:
        article.is_saved = payload.is_saved
        article.saved_at = now if payload.is_saved else None
        if payload.is_saved:
            try:
                archive_service.snapshot_article(db, article, "html")
            except Exception as exc:
                logger.warning("snapshot failed for article %s: %s", article.id, exc)
    changelog.record(
        db,
        user.id,
        "article",
        article.id,
        "upsert",
        payload.model_dump(exclude_unset=True),
    )
    db.add(article)
    db.commit()
    return _article_payload(db, user, article_id)


@router.delete("/articles/{article_id}")
def delete_article(
    article_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    article = _owned_article(db, user, article_id)
    child_ids = db.scalars(select(Article.id).where(Article.parent_id == article.id)).all()
    for child_id in child_ids:
        child = db.get(Article, child_id)
        if not child:
            continue
        for row in db.scalars(select(OverlayAddition).where(OverlayAddition.article_id == child.id)):
            changelog.record(db, user.id, "addition", row.id, "delete", {"article_id": str(child.id)})
            db.delete(row)
        changelog.record(
            db,
            user.id,
            "article",
            child.id,
            "delete",
            {"title": (child.title or "")[:120], "parent_id": str(article.id)},
        )
        db.delete(child)
    for row in db.scalars(select(OverlayAddition).where(OverlayAddition.article_id == article.id)):
        changelog.record(db, user.id, "addition", row.id, "delete", {"article_id": str(article.id)})
        db.delete(row)
    changelog.record(
        db,
        user.id,
        "article",
        article.id,
        "delete",
        {"title": (article.title or "")[:120], "source_kind": getattr(article, "source_kind", None)},
    )
    db.delete(article)
    db.commit()
    return {"ok": True}


@router.patch("/articles/{article_id}/extract", response_model=ExtractOut)
def extract_article(
    article_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ExtractOut:
    article = _owned_article(db, user, article_id)
    article_id_value = article.id
    prev_html = article.content_html
    prev_text = article.content_text
    notice: str | None = None
    try:
        _, notice = extractor.fill_article(db, article, force=True)
    except ExtractFailedError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=EXTRACT_MSG_FAILED) from exc
    try:
        archive_service.snapshot_article(db, article, "html")
    except Exception as exc:
        logger.warning("snapshot after extract failed for article %s: %s", article_id_value, exc)
    db.commit()
    db.refresh(article)
    ok, message = _extract_user_message(prev_html, prev_text, article.content_html, article.content_text)
    if not message:
        message = EXTRACT_MSG_SUCCESS if ok else EXTRACT_MSG_FAILED
    return ExtractOut(
        article=_article_payload(db, user, article_id_value),
        notice=notice,
        ok=ok,
        message=message,
    )


@router.patch("/articles/{article_id}/use-feed-text", response_model=ArticleOut)
def use_feed_text(
    article_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ArticleOut:
    article = _owned_article(db, user, article_id)
    try:
        extractor.restore_feed_body(db, article)
    except ExtractFailedError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=exc.detail) from exc
    db.commit()
    return _article_payload(db, user, article.id)


@router.post("/articles/bulk")
def bulk_update(
    payload: ArticleBulkIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, int]:
    if payload.is_read is None and payload.is_saved is None:
        raise HTTPException(status_code=400, detail="Choose mark read, unread, or save.")
    now = datetime.now(timezone.utc)
    updated = 0
    for article_id in payload.ids:
        article = db.scalar(select(Article).join(Feed).where(Article.id == article_id, Feed.user_id == user.id))
        if not article:
            continue
        changes: dict = {}
        if payload.is_read is not None:
            article.is_read = payload.is_read
            article.read_at = now if payload.is_read else None
            changes["is_read"] = payload.is_read
        if payload.is_saved is not None:
            article.is_saved = payload.is_saved
            article.saved_at = now if payload.is_saved else None
            changes["is_saved"] = payload.is_saved
        changelog.record(db, user.id, "article", article.id, "upsert", changes)
        db.add(article)
        updated += 1
    db.commit()
    return {"updated": updated}


@router.post("/articles/mark-read")
def mark_read(payload: MarkReadIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    updated = 0
    for article_id in payload.ids:
        article = db.scalar(select(Article).join(Feed).where(Article.id == article_id, Feed.user_id == user.id))
        if not article:
            continue
        article.is_read = payload.is_read
        article.read_at = now if payload.is_read else None
        changelog.record(db, user.id, "article", article.id, "upsert", {"is_read": payload.is_read})
        db.add(article)
        updated += 1
    db.commit()
    return {"updated": updated}


@router.put("/articles/{article_id}/tags", response_model=list[TagOut])
def replace_tags(
    article_id: UUID,
    payload: TagIdsIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TagOut]:
    article = _owned_article(db, user, article_id)
    tags = db.scalars(select(Tag).where(Tag.user_id == user.id, Tag.id.in_(payload.tag_ids))).all()
    article.tags = list(tags)
    changelog.record(db, user.id, "article", article.id, "upsert", {"tag_ids": [str(t.id) for t in tags]})
    db.add(article)
    db.commit()
    return [tag_out(tag) for tag in article.tags]


@router.post("/articles/{article_id}/tags", response_model=TagOut)
def attach_tag(
    article_id: UUID,
    payload: TagIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TagOut:
    article = _owned_article(db, user, article_id)
    name = payload.name.strip()
    tag = db.scalar(select(Tag).where(Tag.user_id == user.id, func.lower(Tag.name) == name.lower()))
    if not tag:
        tag = Tag(user_id=user.id, name=name, color=payload.color)
        db.add(tag)
        db.flush()
    if tag not in article.tags:
        article.tags.append(tag)
    changelog.record(db, user.id, "article", article.id, "upsert", {"tag": tag.name})
    db.add(article)
    db.commit()
    return tag_out(tag)


@router.get("/articles/{article_id}/annotations", response_model=list[AnnotationOut])
def list_article_notes(
    article_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[AnnotationOut]:
    article = _owned_article(db, user, article_id)
    return [annotation_out(note, article.title) for note in article.annotations]


@router.post("/articles/{article_id}/annotations", response_model=AnnotationOut, status_code=201)
def create_note(
    article_id: UUID,
    payload: AnnotationIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AnnotationOut:
    article = _owned_article(db, user, article_id)
    note = Annotation(
        user_id=user.id,
        article_id=article.id,
        body=payload.body.strip() or (payload.quote or ""),
        quote=payload.quote,
        kind=payload.kind,
        color=payload.color,
        prefix=payload.prefix,
        suffix=payload.suffix,
    )
    db.add(note)
    db.flush()
    if payload.kind == "highlight":
        overlay = OverlayHighlight(
            user_id=user.id,
            article_id=article.id,
            quote=payload.quote or payload.body,
            note=(payload.body if payload.body.strip() and payload.body.strip() != (payload.quote or "").strip() else None),
            color=payload.color,
            prefix=payload.prefix,
            suffix=payload.suffix,
        )
        db.add(overlay)
        if not article.is_saved:
            article.is_saved = True
            article.saved_at = datetime.now(timezone.utc)
            db.add(article)
    changelog.record(db, user.id, "annotation", note.id, "upsert", {"article_id": str(article.id)})
    db.commit()
    db.refresh(note)
    return annotation_out(note, article.title)


@router.post("/articles/{article_id}/archive", response_model=ArchiveOut)
def archive_article(
    article_id: UUID,
    payload: ArchiveCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ArchiveOut:
    article = _owned_article(db, user, article_id)
    row = archive_service.snapshot_article(db, article, payload.type)
    if row is None:
        raise HTTPException(status_code=400, detail="Nothing stored yet to snapshot.")
    changelog.record(db, user.id, "archive", row.id, "upsert", {"article_id": str(article.id)})
    db.commit()
    db.refresh(row)
    return archive_out(row)


@router.get("/articles/{article_id}/archives", response_model=list[ArchiveOut])
def list_archives(
    article_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ArchiveOut]:
    article = _owned_article(db, user, article_id)
    return [archive_out(row) for row in article.archives]
