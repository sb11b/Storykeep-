from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import settings
from app.models import Feed, Tag, User
from app.services import rss
from app.services import rss_shelves as rss_shelf_service

DEMO_EMAIL = "steve@storykeep.local"
DEMO_PASSWORD = "commonplace"

DEMO_FEEDS = [
    ("News", "https://feeds.bbci.co.uk/news/world/rss.xml", None),
    ("Science", "https://www.nasa.gov/rss/dyn/breaking_news.rss", None),
    ("News", "https://www.theverge.com/rss/index.xml", None),
    ("Science", "https://hnrss.org/frontpage", None),
]


def seed_demo(db: Session) -> User | None:
    if not settings.seed_demo:
        return None
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
    db.flush()
    from app.models import Category

    rss_shelf_service.ensure_user_shelves(db, user)
    inbox = rss_shelf_service.inbox_shelf(db, user)
    categories = {
        row.name: row for row in db.scalars(select(Category).where(Category.shelf_id == inbox.id)).all()
    }
    for tag_name, color in (("to-reread", "#8b3a2a"), ("reference", "#2c4a6e"), ("keep", "#3d6b4f")):
        db.add(Tag(user_id=user.id, name=tag_name, color=color))
    for category_name, url, _title in DEMO_FEEDS:
        category = categories.get(category_name) or rss_shelf_service.uncategorized_category(db, inbox)
        feed = Feed(user_id=user.id, url=url, title=url, shelf_id=inbox.id, category_id=category.id)
        db.add(feed)
        db.flush()
        try:
            rss.refresh_feed(db, feed, extract=False, limit=20)
        except Exception:
            db.commit()
    db.commit()
    return user
