"""Move steve@storykeep.local library to another user, then restore demo defaults."""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Category, Feed, Tag, User
from app.seed import CATEGORY_COLORS, DEMO_EMAIL, DEMO_FEEDS, DEMO_PASSWORD
from app.services import rss
from app.auth import hash_password

DEFAULT_TAG_COLORS = (("to-reread", "#8b3a2a"), ("reference", "#2c4a6e"), ("keep", "#3d6b4f"))

OWNERSHIP_TABLES = (
    "categories",
    "feeds",
    "tags",
    "annotations",
    "highlights",
    "storykeep_notes",
    "corrections",
    "note_media",
    "backups",
    "change_log",
    "sync_devices",
)


def restore_demo_defaults(db: Session, user: User) -> None:
    categories: dict[str, Category] = {}
    for name, color in CATEGORY_COLORS.items():
        category = db.scalar(select(Category).where(Category.user_id == user.id, Category.name == name))
        if not category:
            category = Category(user_id=user.id, name=name, color=color)
            db.add(category)
            db.flush()
        categories[name] = category
    for tag_name, color in DEFAULT_TAG_COLORS:
        tag = db.scalar(select(Tag).where(Tag.user_id == user.id, Tag.name == tag_name))
        if not tag:
            db.add(Tag(user_id=user.id, name=tag_name, color=color))
    db.flush()
    for category_name, url, _title in DEMO_FEEDS:
        feed = db.scalar(select(Feed).where(Feed.user_id == user.id, Feed.url == url))
        if feed:
            continue
        feed = Feed(
            user_id=user.id,
            url=url,
            title=url,
            category_id=categories[category_name].id,
            is_active=True,
        )
        db.add(feed)
        db.flush()
        try:
            rss.refresh_feed(db, feed, extract=False, limit=20)
        except Exception:
            db.commit()
    db.commit()


def transfer_library(db: Session, source_email: str, dest_email: str) -> dict[str, int]:
    source = db.scalar(select(User).where(User.email == source_email))
    dest = db.scalar(select(User).where(User.email == dest_email))
    if not source or not dest:
        raise ValueError(f"Need both users: {source_email!r} -> {dest_email!r}")
    moved: dict[str, int] = {}
    bind = db.get_bind()
    for table in OWNERSHIP_TABLES:
        result = bind.execute(
            text(f"UPDATE {table} SET user_id = :dest WHERE user_id = :src"),
            {"dest": dest.id, "src": source.id},
        )
        moved[table] = result.rowcount or 0
    db.commit()
    return moved


def ensure_demo_user(db: Session) -> User:
    user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if user:
        user.is_demo_locked = True
        db.commit()
        return user
    user = User(
        email=DEMO_EMAIL,
        password_hash=hash_password(DEMO_PASSWORD),
        display_name="Steve",
        preferences={"theme": "paper", "items_per_page": 40, "mark_read_on_open": True},
        is_demo_locked=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
