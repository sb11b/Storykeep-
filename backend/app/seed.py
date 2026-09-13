from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User

DEMO_EMAIL = "steve@storykeep.local"


def seed_demo(db: Session) -> User | None:
    """Keep any legacy demo row locked; never create or enable demo login."""
    if not settings.seed_demo:
        return None
    user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
    if not user:
        return None
    user.is_demo_locked = True
    db.commit()
    return user
