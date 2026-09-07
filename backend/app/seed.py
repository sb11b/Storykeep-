from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import settings
from app.models import Category, Feed, Tag, User
from app.services import rss

DEMO_EMAIL = "steve@storykeep.local"
DEMO_PASSWORD = "commonplace"

DEMO_FEEDS = [
    ("Technology", "https://hnrss.org/frontpage", None),
    ("Technology", "https://www.theverge.com/rss/index.xml", None),
    ("Science", "https://www.nasa.gov/rss/dyn/breaking_news.rss", None),
    ("News", "https://feeds.bbci.co.uk/news/world/rss.xml", None),
]

CATEGORY_COLORS = {
    "Technology": "#c45c26",
    "Science": "#3d6b4f",
    "News": "#2c4a6e",
}


def seed_demo(db: Session) -> User | None:
    if not settings.seed_demo:
        return None
    user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if user:
        return user
    user = User(
        email=DEMO_EMAIL,
        password_hash=hash_password(DEMO_PASSWORD),
        display_name="Steve",
        preferences={"theme": "paper", "items_per_page": 40, "mark_read_on_open": True},
    )
    db.add(user)
    db.flush()
    categories: dict[str, Category] = {}
    for name, color in CATEGORY_COLORS.items():
        category = Category(user_id=user.id, name=name, color=color)
        db.add(category)
        db.flush()
        categories[name] = category
    for tag_name, color in (("to-reread", "#8b3a2a"), ("reference", "#2c4a6e"), ("keep", "#3d6b4f")):
        db.add(Tag(user_id=user.id, name=tag_name, color=color))
    for category_name, url, _title in DEMO_FEEDS:
        feed = Feed(user_id=user.id, url=url, title=url, category_id=categories[category_name].id)
        db.add(feed)
        db.flush()
        try:
            rss.refresh_feed(db, feed, extract=False, limit=20)
        except Exception:
            db.commit()
    db.commit()
    return user
