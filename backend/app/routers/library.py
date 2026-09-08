from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.deps import get_current_user
from app.models import Annotation, Archive, Article, Category, Feed, OverlayHighlight, Tag, User
from app.presenters import annotation_out, article_list_item
from app.services.notes_feed import notes_feed_page
from app.services.destination import shelf_count
from app.schemas import (
    AnnotationIn,
    AnnotationOut,
    CategoryIn,
    CategoryOut,
    Page,
    PreferencesIn,
    SearchHit,
    StatsOut,
    TagIn,
    TagMergeIn,
    TagOut,
)
from app.services import changelog
from app.services.overlay_search import article_search_match, overlay_text_subquery

router = APIRouter(tags=["library"])


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[CategoryOut]:
    categories = db.scalars(
        select(Category).where(Category.user_id == user.id).order_by(Category.sort_order, Category.name)
    ).all()
    out: list[CategoryOut] = []
    for category in categories:
        count = db.scalar(select(func.count()).select_from(Feed).where(Feed.category_id == category.id)) or 0
        out.append(CategoryOut(id=category.id, name=category.name, color=category.color, sort_order=category.sort_order, feed_count=count))
    return out


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(
    payload: CategoryIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> CategoryOut:
    existing = db.scalar(select(Category).where(Category.user_id == user.id, Category.name == payload.name))
    if existing:
        raise HTTPException(status_code=409, detail="Category already exists")
    category = Category(user_id=user.id, **payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return CategoryOut(id=category.id, name=category.name, color=category.color, sort_order=category.sort_order, feed_count=0)


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: UUID,
    payload: CategoryIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CategoryOut:
    category = db.get(Category, category_id)
    if not category or category.user_id != user.id:
        raise HTTPException(status_code=404, detail="Category not found")
    for key, value in payload.model_dump().items():
        setattr(category, key, value)
    db.add(category)
    db.commit()
    db.refresh(category)
    count = db.scalar(select(func.count()).select_from(Feed).where(Feed.category_id == category.id)) or 0
    return CategoryOut(id=category.id, name=category.name, color=category.color, sort_order=category.sort_order, feed_count=count)


@router.delete("/categories/{category_id}")
def delete_category(
    category_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict[str, bool]:
    category = db.get(Category, category_id)
    if not category or category.user_id != user.id:
        raise HTTPException(status_code=404, detail="Category not found")
    db.delete(category)
    db.commit()
    return {"ok": True}


@router.get("/tags", response_model=list[TagOut])
def list_tags(
    q: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TagOut]:
    stmt = select(Tag).where(Tag.user_id == user.id).order_by(Tag.name)
    if q and q.strip():
        stmt = stmt.where(Tag.name.ilike(f"%{q.strip()}%"))
    tags = db.scalars(stmt).all()
    out: list[TagOut] = []
    for tag in tags:
        count = db.scalar(
            select(func.count()).select_from(Article).join(Article.tags).where(Tag.id == tag.id)
        ) or 0
        out.append(TagOut(id=tag.id, name=tag.name, color=tag.color, article_count=count))
    return out


@router.post("/tags", response_model=TagOut, status_code=201)
def create_tag(payload: TagIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> TagOut:
    existing = db.scalar(
        select(Tag).where(Tag.user_id == user.id, func.lower(Tag.name) == payload.name.strip().lower())
    )
    if existing:
        raise HTTPException(status_code=409, detail="Tag already exists")
    tag = Tag(user_id=user.id, name=payload.name.strip(), color=payload.color)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return TagOut(id=tag.id, name=tag.name, color=tag.color, article_count=0)


@router.patch("/tags/{tag_id}", response_model=TagOut)
def update_tag(
    tag_id: UUID, payload: TagIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> TagOut:
    tag = db.get(Tag, tag_id)
    if not tag or tag.user_id != user.id:
        raise HTTPException(status_code=404, detail="Tag not found")
    clash = db.scalar(
        select(Tag).where(
            Tag.user_id == user.id,
            func.lower(Tag.name) == payload.name.strip().lower(),
            Tag.id != tag.id,
        )
    )
    if clash:
        raise HTTPException(status_code=409, detail="Another tag already has that name. Merge them instead.")
    tag.name = payload.name.strip()
    tag.color = payload.color
    db.add(tag)
    db.commit()
    db.refresh(tag)
    count = db.scalar(select(func.count()).select_from(Article).join(Article.tags).where(Tag.id == tag.id)) or 0
    return TagOut(id=tag.id, name=tag.name, color=tag.color, article_count=count)


@router.post("/tags/{tag_id}/merge", response_model=TagOut)
def merge_tag(
    tag_id: UUID, payload: TagMergeIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> TagOut:
    source = db.scalar(select(Tag).options(selectinload(Tag.articles)).where(Tag.id == tag_id, Tag.user_id == user.id))
    dest = db.get(Tag, payload.into_tag_id)
    if not source or source.user_id != user.id:
        raise HTTPException(status_code=404, detail="Tag not found")
    if not dest or dest.user_id != user.id:
        raise HTTPException(status_code=404, detail="Target tag not found")
    if source.id == dest.id:
        raise HTTPException(status_code=400, detail="Pick a different tag to merge into.")
    for article in list(source.articles):
        if dest not in article.tags:
            article.tags.append(dest)
        if source in article.tags:
            article.tags.remove(source)
        db.add(article)
    changelog.record(db, user.id, "tag", dest.id, "upsert", {"merged_from": str(source.id)})
    db.delete(source)
    db.commit()
    db.refresh(dest)
    count = db.scalar(select(func.count()).select_from(Article).join(Article.tags).where(Tag.id == dest.id)) or 0
    return TagOut(id=dest.id, name=dest.name, color=dest.color, article_count=count)


@router.delete("/tags/{tag_id}")
def delete_tag(tag_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, bool]:
    tag = db.get(Tag, tag_id)
    if not tag or tag.user_id != user.id:
        raise HTTPException(status_code=404, detail="Tag not found")
    db.delete(tag)
    db.commit()
    return {"ok": True}


@router.get("/annotations", response_model=Page[AnnotationOut])
def list_notes(
    limit: int = Query(default=40, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[AnnotationOut]:
    items, total = notes_feed_page(db, user, limit, offset)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.patch("/annotations/{note_id}", response_model=AnnotationOut)
def update_note(
    note_id: UUID, payload: AnnotationIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> AnnotationOut:
    note = db.get(Annotation, note_id)
    if not note or note.user_id != user.id:
        raise HTTPException(status_code=404, detail="Note not found")
    note.body = payload.body
    note.quote = payload.quote
    note.updated_at = datetime.now(timezone.utc)
    changelog.record(db, user.id, "annotation", note.id, "upsert", {"body": note.body})
    db.add(note)
    db.commit()
    db.refresh(note)
    return annotation_out(note)


@router.delete("/annotations/{note_id}")
def delete_note(note_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, bool]:
    note = db.get(Annotation, note_id)
    if not note or note.user_id != user.id:
        raise HTTPException(status_code=404, detail="Note not found")
    if note.kind == "highlight" and note.quote:
        extras = db.scalars(
            select(OverlayHighlight).where(
                OverlayHighlight.user_id == user.id,
                OverlayHighlight.article_id == note.article_id,
                OverlayHighlight.quote == note.quote,
            )
        ).all()
        for row in extras:
            db.delete(row)
    changelog.record(db, user.id, "annotation", note.id, "delete")
    db.delete(note)
    db.commit()
    return {"ok": True}


@router.get("/archives/{archive_id}")
def get_archive(archive_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    row = db.get(Archive, archive_id)
    if not row:
        raise HTTPException(status_code=404, detail="Archive not found")
    article = db.scalar(select(Article).join(Feed).where(Article.id == row.article_id, Feed.user_id == user.id))
    if not article:
        raise HTTPException(status_code=404, detail="Archive not found")
    return {
        "id": str(row.id),
        "article_id": str(row.article_id),
        "archive_type": row.archive_type,
        "content": row.content,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/search", response_model=Page[SearchHit])
def search(
    q: str = Query(min_length=1),
    saved: bool | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Page[SearchHit]:
    tsquery = func.plainto_tsquery("english", q)
    rank = func.ts_rank_cd(Article.search_vector, tsquery)
    notes, highlights, additions, corrections = overlay_text_subquery(user.id)
    headline = func.ts_headline(
        "english",
        func.concat(
            func.coalesce(Article.content_text, Article.summary, Article.title, ""),
            " ",
            func.coalesce(notes, ""),
            " ",
            func.coalesce(highlights, ""),
            " ",
            func.coalesce(additions, ""),
            " ",
            func.coalesce(corrections, ""),
        ),
        tsquery,
        "StartSel=<mark>, StopSel=</mark>, MaxWords=32, MinWords=12",
    )
    stmt = (
        select(Article, rank, headline)
        .join(Feed)
        .where(Feed.user_id == user.id)
        .where(article_search_match(user.id, tsquery, q))
        .options(selectinload(Article.feed), selectinload(Article.tags))
        .order_by(rank.desc(), Article.published_at.desc().nulls_last())
    )
    if saved is not None:
        stmt = stmt.where(Article.is_saved.is_(saved))
    rows = db.execute(stmt.offset(offset).limit(limit)).all()
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).with_only_columns(Article.id).subquery())) or 0
    items = [
        SearchHit(article=article_list_item(article), rank=float(score or 0), headline=snippet)
        for article, score, snippet in rows
    ]
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/preferences")
def get_preferences(user: User = Depends(get_current_user)) -> dict:
    return user.preferences or {}


@router.put("/preferences")
def put_preferences(
    payload: PreferencesIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict:
    current = dict(user.preferences or {})
    current.update({k: v for k, v in payload.model_dump().items() if v is not None})
    user.preferences = current
    db.add(user)
    db.commit()
    return current


@router.get("/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> StatsOut:
    feed_ids = select(Feed.id).where(Feed.user_id == user.id)
    article_base = select(Article).where(Article.feed_id.in_(feed_ids))
    return StatsOut(
        feed_count=db.scalar(select(func.count()).select_from(Feed).where(Feed.user_id == user.id)) or 0,
        article_count=db.scalar(select(func.count()).select_from(article_base.subquery())) or 0,
        unread_count=db.scalar(
            select(func.count()).select_from(article_base.where(Article.is_read.is_(False)).subquery())
        )
        or 0,
        saved_count=db.scalar(
            select(func.count()).select_from(article_base.where(Article.is_saved.is_(True)).subquery())
        )
        or 0,
        annotation_count=shelf_count(db, user, "notes"),
        vault_count=shelf_count(db, user, "vault"),
        additions_count=shelf_count(db, user, "additions"),
        books_count=shelf_count(db, user, "books"),
        schoolwork_count=shelf_count(db, user, "schoolwork"),
        oldest_saved_at=db.scalar(
            select(func.min(Article.saved_at)).where(Article.feed_id.in_(feed_ids), Article.is_saved.is_(True))
        ),
    )
