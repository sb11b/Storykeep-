"""RSS workspace shelves and per-shelf feed categories."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Article, Category, Feed, RssShelf, User

UNCATEGORIZED = "Uncategorized"
SEED_SHELVES: list[tuple[str, int]] = [
    ("Inbox", 0),
    ("School", 1),
    ("News", 2),
    ("Book", 3),
]
INBOX_STARTER_CATEGORIES: list[tuple[str, int]] = [
    ("News", 10),
    ("Science", 20),
    (UNCATEGORIZED, 99),
]


def list_shelves(db: Session, user: User) -> list[RssShelf]:
    ensure_user_shelves(db, user)
    return db.scalars(
        select(RssShelf).where(RssShelf.user_id == user.id).order_by(RssShelf.sort_order, RssShelf.name)
    ).all()


def shelf_by_id(db: Session, user: User, shelf_id: UUID) -> RssShelf | None:
    row = db.get(RssShelf, shelf_id)
    if not row or row.user_id != user.id:
        return None
    return row


def inbox_shelf(db: Session, user: User) -> RssShelf:
    ensure_user_shelves(db, user)
    row = db.scalar(select(RssShelf).where(RssShelf.user_id == user.id, RssShelf.name == "Inbox").limit(1))
    if not row:
        raise RuntimeError("Inbox shelf missing after ensure")
    return row


def uncategorized_category(db: Session, shelf: RssShelf) -> Category:
    row = db.scalar(
        select(Category).where(
            Category.shelf_id == shelf.id,
            Category.is_system.is_(True),
            Category.name == UNCATEGORIZED,
        )
    )
    if row:
        return row
    row = Category(
        user_id=shelf.user_id,
        shelf_id=shelf.id,
        name=UNCATEGORIZED,
        sort_order=99,
        is_system=True,
    )
    db.add(row)
    db.flush()
    return row


def ensure_user_shelves(db: Session, user: User) -> None:
    count = db.scalar(select(func.count()).select_from(RssShelf).where(RssShelf.user_id == user.id)) or 0
    if count:
        for shelf in db.scalars(select(RssShelf).where(RssShelf.user_id == user.id)).all():
            uncategorized_category(db, shelf)
        db.flush()
        return
    shelves = _create_seed_shelves(db, user)
    inbox = shelves[0]
    legacy = db.scalars(select(Category).where(Category.user_id == user.id, Category.shelf_id.is_(None))).all()
    if legacy:
        for category in legacy:
            category.shelf_id = inbox.id
            if category.name == UNCATEGORIZED:
                category.is_system = True
            db.add(category)
    else:
        for cat_name, sort_order in INBOX_STARTER_CATEGORIES:
            db.add(
                Category(
                    user_id=user.id,
                    shelf_id=inbox.id,
                    name=cat_name,
                    sort_order=sort_order,
                    is_system=cat_name == UNCATEGORIZED,
                )
            )
    for shelf in shelves:
        uncategorized_category(db, shelf)
    uncategorized = uncategorized_category(db, inbox)
    for feed in db.scalars(select(Feed).where(Feed.user_id == user.id)).all():
        if not feed.shelf_id:
            feed.shelf_id = inbox.id
        if not feed.category_id:
            feed.category_id = uncategorized.id
        db.add(feed)
    db.flush()


def _create_seed_shelves(db: Session, user: User) -> list[RssShelf]:
    shelves: list[RssShelf] = []
    for name, sort_order in SEED_SHELVES:
        shelf = RssShelf(user_id=user.id, name=name, sort_order=sort_order)
        db.add(shelf)
        db.flush()
        shelves.append(shelf)
    return shelves


def validate_category_on_shelf(db: Session, user: User, shelf_id: UUID, category_id: UUID) -> Category:
    category = db.get(Category, category_id)
    if not category or category.user_id != user.id or category.shelf_id != shelf_id:
        raise ValueError("Category not found on this shelf")
    return category


def category_unread_count(db: Session, category_id: UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Article)
            .join(Feed, Feed.id == Article.feed_id)
            .where(Feed.category_id == category_id, Article.is_read.is_(False))
        )
        or 0
    )


def shelf_feed_count(db: Session, shelf_id: UUID) -> int:
    return db.scalar(select(func.count()).select_from(Feed).where(Feed.shelf_id == shelf_id)) or 0


def shelf_unread_count(db: Session, shelf_id: UUID) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Article)
            .join(Feed, Feed.id == Article.feed_id)
            .where(Feed.shelf_id == shelf_id, Article.is_read.is_(False))
        )
        or 0
    )


def reassign_feeds_to_uncategorized(db: Session, category: Category) -> None:
    if not category.shelf_id:
        return
    shelf = db.get(RssShelf, category.shelf_id)
    if not shelf:
        return
    uncategorized = uncategorized_category(db, shelf)
    for feed in db.scalars(select(Feed).where(Feed.category_id == category.id)).all():
        feed.category_id = uncategorized.id
        db.add(feed)


def move_feeds_to_inbox(db: Session, user: User, from_shelf: RssShelf) -> None:
    inbox = inbox_shelf(db, user)
    uncategorized = uncategorized_category(db, inbox)
    for feed in db.scalars(select(Feed).where(Feed.shelf_id == from_shelf.id)).all():
        feed.shelf_id = inbox.id
        feed.category_id = uncategorized.id
        db.add(feed)
