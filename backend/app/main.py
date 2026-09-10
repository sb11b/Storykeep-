from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select, text

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Feed
from app.routers import articles, auth, backups, chat, feeds, library, overlay, stt, sync, tts
from app.seed import seed_demo
from app.services import rss

logger = logging.getLogger(__name__)
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


def _try_sql(statement: str) -> None:
    with engine.connect() as connection:
        try:
            connection.execute(text(statement))
            connection.commit()
        except Exception as exc:
            logger.warning("Skipping SQL (%s): %s", statement.split(" ", 3)[2] if "EXTENSION" in statement else statement[:48], exc)
            connection.rollback()


def _create_schema() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    _try_sql("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    _try_sql("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    with engine.begin() as connection:
        Base.metadata.create_all(bind=connection)
        connection.execute(text("CREATE INDEX IF NOT EXISTS articles_search_idx ON articles USING GIN (search_vector)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS change_log_user_cursor_idx ON change_log (user_id, id)"))
    _try_sql("ALTER TABLE annotations ADD COLUMN IF NOT EXISTS kind VARCHAR(16) DEFAULT 'note'")
    _try_sql("ALTER TABLE annotations ADD COLUMN IF NOT EXISTS color VARCHAR(24)")
    _try_sql("ALTER TABLE annotations ADD COLUMN IF NOT EXISTS prefix TEXT")
    _try_sql("ALTER TABLE annotations ADD COLUMN IF NOT EXISTS suffix TEXT")
    _try_sql("UPDATE annotations SET kind = 'note' WHERE kind IS NULL")
    _try_sql("ALTER TABLE articles ADD COLUMN IF NOT EXISTS source_kind VARCHAR(16) DEFAULT 'rss'")
    _try_sql("ALTER TABLE articles ADD COLUMN IF NOT EXISTS source_ref TEXT")
    _try_sql("ALTER TABLE articles ADD COLUMN IF NOT EXISTS parent_id UUID")
    _try_sql("ALTER TABLE articles ADD COLUMN IF NOT EXISTS obsidian_path TEXT")
    _try_sql("ALTER TABLE articles ADD COLUMN IF NOT EXISTS destination VARCHAR(16)")
    _try_sql("ALTER TABLE articles ADD COLUMN IF NOT EXISTS is_correction BOOLEAN DEFAULT FALSE")
    _try_sql("ALTER TABLE storykeep_notes ADD COLUMN IF NOT EXISTS destination VARCHAR(16) DEFAULT 'additions'")
    _try_sql("ALTER TABLE storykeep_notes ADD COLUMN IF NOT EXISTS is_correction BOOLEAN DEFAULT FALSE")
    _try_sql(
        "UPDATE articles SET destination = 'additions' WHERE guid LIKE 'storykeep-note:%' AND (destination IS NULL OR destination = '')"
    )
    _try_sql(
        "UPDATE articles SET destination = 'books' WHERE guid LIKE 'storykeep-note:%' AND source_kind = 'textbook' AND (destination IS NULL OR destination = 'additions')"
    )
    _try_sql("UPDATE articles SET is_correction = FALSE WHERE is_correction IS NULL")
    _try_sql("UPDATE storykeep_notes SET destination = 'additions' WHERE destination IS NULL OR destination = ''")
    _try_sql("UPDATE storykeep_notes SET is_correction = FALSE WHERE is_correction IS NULL")
    _try_sql("UPDATE articles SET source_kind = 'rss' WHERE source_kind IS NULL")
    _try_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_demo_locked BOOLEAN DEFAULT FALSE")
    _try_sql("UPDATE users SET is_demo_locked = TRUE WHERE lower(email) = 'steve@storykeep.local'")
    _try_sql("UPDATE users SET is_demo_locked = FALSE WHERE lower(email) = 'stevebitsko@duck.com'")


def _seed_in_background() -> None:
    if not settings.seed_demo:
        return
    db = SessionLocal()
    try:
        seed_demo(db)
    except Exception:
        logger.exception("Demo seed failed")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    _create_schema()
    threading.Thread(target=_seed_in_background, daemon=True, name="storykeep-seed").start()
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
    expose_headers=["X-TTS-Chunk", "X-TTS-Chunks"],
)

API = "/api/v1"
app.include_router(auth.router, prefix=API)
app.include_router(feeds.router, prefix=API)
app.include_router(articles.router, prefix=API)
app.include_router(overlay.router, prefix=API)
app.include_router(library.router, prefix=API)
app.include_router(sync.router, prefix=API)
app.include_router(backups.router, prefix=API)
app.include_router(tts.router, prefix=API)
app.include_router(chat.router, prefix=API)
app.include_router(stt.router, prefix=API)


def _build_info() -> dict[str, str]:
    path = Path(__file__).resolve().parent / "build-info.json"
    if path.is_file():
        try:
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
            return {
                "build": str(data.get("sha") or "unknown"),
                "built_at": str(data.get("time") or ""),
            }
        except (OSError, ValueError, TypeError):
            pass
    return {"build": "unknown", "built_at": ""}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", **_build_info()}


def _static_headers(path: Path) -> dict[str, str]:
    suffix = path.suffix.lower()
    if suffix in {".html", ".js", ".css"}:
        return {"Cache-Control": "no-store"}
    return {"Cache-Control": "public, max-age=3600"}


def _register_frontend(app: FastAPI) -> None:
    directory = Path(settings.frontend_dir) if settings.frontend_dir else None
    if not directory or not directory.is_dir():
        return

    @app.get("/{full_path:path}")
    def frontend_page(full_path: str):
        if full_path in {"api", "health"} or full_path.startswith("api/"):
            return {"detail": "Not found"}
        direct = directory / full_path
        if direct.is_file():
            return FileResponse(direct, headers=_static_headers(direct))
        nested = directory / full_path / "index.html"
        if nested.is_file():
            return FileResponse(nested, headers=_static_headers(nested))
        html = directory / f"{full_path}.html"
        if html.is_file():
            return FileResponse(html, headers=_static_headers(html))
        index = directory / "index.html"
        return FileResponse(index, headers=_static_headers(index))


_register_frontend(app)
