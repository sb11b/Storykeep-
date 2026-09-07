from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Feed, ensure_search_index
from app.routers import articles, auth, backups, feeds, library, sync
from app.seed import seed_demo
from app.services import rss

scheduler = BackgroundScheduler()


def refresh_due_feeds() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        feeds_due = db.scalars(select(Feed).where(Feed.is_active.is_(True))).all()
        for feed in feeds_due:
            interval = timedelta(minutes=feed.fetch_interval_minutes or 60)
            if feed.last_fetched_at and now - feed.last_fetched_at < interval:
                continue
            rss.refresh_feed(db, feed, extract=settings.extract_on_import, limit=30)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        Base.metadata.create_all(bind=connection)
        ensure_search_index(connection)
    db = SessionLocal()
    try:
        seed_demo(db)
    finally:
        db.close()
    scheduler.add_job(refresh_due_feeds, "interval", minutes=settings.refresh_minutes, id="refresh")
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Storykeep", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API = "/api/v1"
app.include_router(auth.router, prefix=API)
app.include_router(feeds.router, prefix=API)
app.include_router(articles.router, prefix=API)
app.include_router(library.router, prefix=API)
app.include_router(sync.router, prefix=API)
app.include_router(backups.router, prefix=API)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
