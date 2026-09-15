from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import select, text
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings
from app.http_limits import PAYLOAD_TOO_LARGE, LimitChatBodyMiddleware, log_chat_exception
from app.database import Base, SessionLocal, engine
from app.models import Feed
from app.routers import articles, auth, backups, calendar, chat, feeds, junior_jobs, library, overlay, school, stt, sync, tts
from app.seed import seed_demo
from app.services import rss
from app.services.backup import run_scheduled_s3_dumps

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()


class NormalizeApiPathMiddleware:
    """Strip trailing slashes on /api/* so PATCH routes are not shadowed by the SPA GET catch-all."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope.get("path", "")
            if path.startswith("/api/") and path.endswith("/") and len(path) > 1:
                normalized = path.rstrip("/")
                scope["path"] = normalized
                scope["raw_path"] = normalized.encode("utf-8")
        await self.app(scope, receive, send)


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
    _try_sql("ALTER TABLE articles ADD COLUMN IF NOT EXISTS feed_html TEXT")
    _try_sql("ALTER TABLE articles ADD COLUMN IF NOT EXISTS feed_text TEXT")
    _try_sql("ALTER TABLE articles ADD COLUMN IF NOT EXISTS folder_id UUID")
    _try_sql("ALTER TABLE articles ADD COLUMN IF NOT EXISTS offline_view VARCHAR(16)")
    _try_sql("ALTER TABLE articles ADD COLUMN IF NOT EXISTS offline_archive_id UUID")
    _try_sql("ALTER TABLE articles ALTER COLUMN feed_id DROP NOT NULL")
    _try_sql("ALTER TABLE articles DROP CONSTRAINT IF EXISTS articles_feed_id_fkey")
    _try_sql(
        "ALTER TABLE articles ADD CONSTRAINT articles_feed_id_fkey "
        "FOREIGN KEY (feed_id) REFERENCES feeds(id) ON DELETE SET NULL"
    )
    _try_sql("ALTER TABLE folders DROP CONSTRAINT IF EXISTS folders_user_id_name_key")
    _try_sql("DROP INDEX IF EXISTS folders_user_id_name_key")
    _try_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS folders_user_shelf_name_idx ON folders (user_id, shelf, name)"
    )
    _try_sql(
        "UPDATE articles SET feed_html = summary "
        "WHERE feed_html IS NULL AND source_kind = 'rss' AND summary IS NOT NULL AND length(summary) > 120"
    )
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
    _try_sql(
        "CREATE TABLE IF NOT EXISTS rss_shelves ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "name TEXT NOT NULL, icon TEXT, color TEXT, sort_order INTEGER DEFAULT 0, "
        "created_at TIMESTAMPTZ DEFAULT now(), "
        "UNIQUE(user_id, name))"
    )
    _try_sql("ALTER TABLE categories ADD COLUMN IF NOT EXISTS shelf_id UUID REFERENCES rss_shelves(id) ON DELETE CASCADE")
    _try_sql("ALTER TABLE categories ADD COLUMN IF NOT EXISTS is_system BOOLEAN DEFAULT FALSE")
    _try_sql("ALTER TABLE feeds ADD COLUMN IF NOT EXISTS shelf_id UUID REFERENCES rss_shelves(id) ON DELETE CASCADE")
    _try_sql("ALTER TABLE categories DROP CONSTRAINT IF EXISTS categories_user_id_name_key")
    _try_sql("CREATE UNIQUE INDEX IF NOT EXISTS categories_shelf_name_idx ON categories (shelf_id, name)")
    _try_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_media_id UUID REFERENCES note_media(id) ON DELETE SET NULL")
    _try_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS birthdate DATE")
    _try_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret_encrypted TEXT")
    _try_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN DEFAULT FALSE")
    _try_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS email_otp_enabled BOOLEAN DEFAULT FALSE")
    _try_sql("ALTER TABLE users ADD COLUMN IF NOT EXISTS backup_code_hashes JSONB DEFAULT '[]'::jsonb")
    _try_sql("DROP TABLE IF EXISTS google_calendar_accounts")
    _try_sql(
        "CREATE TABLE IF NOT EXISTS fastmail_calendar_accounts ("
        "user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, "
        "fastmail_email TEXT NOT NULL, token_encrypted TEXT NOT NULL, "
        "calendar_href TEXT NOT NULL DEFAULT '', calendar_name TEXT, "
        "created_at TIMESTAMPTZ DEFAULT now(), updated_at TIMESTAMPTZ DEFAULT now())"
    )
    _try_sql(
        "CREATE TABLE IF NOT EXISTS auth_challenges ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "kind VARCHAR(32) NOT NULL, code_hash TEXT, payload JSONB, "
        "attempts INTEGER DEFAULT 0, expires_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ DEFAULT now())"
    )
    _try_sql(
        "CREATE TABLE IF NOT EXISTS grok_conversations ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
        "title TEXT NOT NULL DEFAULT 'New chat', "
        "pane TEXT, "
        "created_at TIMESTAMPTZ DEFAULT now(), "
        "updated_at TIMESTAMPTZ DEFAULT now())"
    )
    _try_sql(
        "CREATE INDEX IF NOT EXISTS grok_conversations_user_updated_idx "
        "ON grok_conversations (user_id, updated_at DESC)"
    )
    _try_sql(
        "CREATE TABLE IF NOT EXISTS grok_messages ("
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid(), "
        "conversation_id UUID NOT NULL REFERENCES grok_conversations(id) ON DELETE CASCADE, "
        "role VARCHAR(16) NOT NULL, "
        "content TEXT NOT NULL, "
        "created_at TIMESTAMPTZ DEFAULT now())"
    )
    _try_sql(
        "CREATE INDEX IF NOT EXISTS grok_messages_conversation_created_idx "
        "ON grok_messages (conversation_id, created_at)"
    )
    _try_sql("ALTER TABLE grok_conversations ADD COLUMN IF NOT EXISTS model VARCHAR(64) DEFAULT 'auto'")
    _try_sql("ALTER TABLE grok_conversations ADD COLUMN IF NOT EXISTS last_model VARCHAR(64)")
    _try_sql("ALTER TABLE grok_conversations ADD COLUMN IF NOT EXISTS reasoning VARCHAR(16) DEFAULT 'auto'")
    _try_sql("ALTER TABLE grok_conversations ADD COLUMN IF NOT EXISTS last_reasoning VARCHAR(16)")
    _try_sql("UPDATE grok_conversations SET reasoning = 'auto' WHERE reasoning IS NULL")
    _try_sql("UPDATE grok_conversations SET model = 'auto' WHERE model IS NULL")
    _try_sql(
        "ALTER TABLE grok_conversations ADD COLUMN IF NOT EXISTS recap_question BOOLEAN NOT NULL DEFAULT false"
    )
    _try_sql(
        "ALTER TABLE grok_conversations ADD COLUMN IF NOT EXISTS saved_note_id UUID REFERENCES articles(id) ON DELETE SET NULL"
    )
    _try_sql(
        "ALTER TABLE junior_jobs ADD COLUMN IF NOT EXISTS web_search BOOLEAN NOT NULL DEFAULT false"
    )


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
    scheduler.add_job(
        run_scheduled_s3_dumps,
        "interval",
        minutes=60,
        id="scheduled-s3-dumps",
        coalesce=True,
        max_instances=1,
    )
    from app.services.junior_jobs import run_due_jobs

    scheduler.add_job(
        run_due_jobs,
        "interval",
        minutes=1,
        id="junior-jobs",
        coalesce=True,
        max_instances=1,
    )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Storykeep", version="0.1.0", lifespan=lifespan)


@app.exception_handler(StarletteHTTPException)
async def http_exception_with_message(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """TTS routes and chat 504 expose {message} for readable client toasts."""
    detail = exc.detail
    if isinstance(detail, list):
        message = "; ".join(str(item) for item in detail)
    else:
        message = str(detail)
    path = request.url.path.rstrip("/")
    if "/tts" in path:
        return JSONResponse(status_code=exc.status_code, content={"message": message, "detail": detail})
    if request.method == "POST" and path == "/api/v1/chat" and exc.status_code == 504:
        return JSONResponse(status_code=504, content={"message": message})
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


@app.exception_handler(MemoryError)
async def memory_error_handler(request: Request, _exc: MemoryError) -> JSONResponse:
    log_chat_exception("memory error", path=request.url.path)
    return JSONResponse(
        status_code=413,
        content={"detail": PAYLOAD_TOO_LARGE, "code": "payload_too_large"},
    )


def _chat_message_too_long(exc: RequestValidationError) -> bool:
    for err in exc.errors():
        loc = err.get("loc") or ()
        msg = str(err.get("msg") or "").lower()
        if "message" in loc and ("at most" in msg or "too long" in msg or err.get("type") == "string_too_long"):
            return True
        if "at most" in msg and "character" in msg:
            return True
    return False


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    path = request.url.path.rstrip("/")
    if request.method == "POST" and path == "/api/v1/chat" and _chat_message_too_long(exc):
        return JSONResponse(
            status_code=413,
            content={"detail": PAYLOAD_TOO_LARGE, "code": "payload_too_large"},
        )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, StarletteHTTPException):
        return await http_exception_with_message(request, exc)
    log_chat_exception("unhandled", path=request.url.path, method=request.method)
    path = request.url.path.rstrip("/")
    if path in {"/health", "/api/health"}:
        return JSONResponse(status_code=200, content=health_payload())
    return JSONResponse(status_code=500, content={"detail": "Something went wrong."})


app.add_middleware(NormalizeApiPathMiddleware)
app.add_middleware(LimitChatBodyMiddleware)

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
from app.routers.auth import get_me, patch_me  # noqa: E402
from app.schemas import ProfileOut  # noqa: E402

app.add_api_route(f"{API}/me", get_me, methods=["GET"], tags=["auth"], response_model=ProfileOut)
app.add_api_route(f"{API}/me", patch_me, methods=["PATCH"], tags=["auth"], response_model=ProfileOut)
app.include_router(feeds.router, prefix=API)
app.include_router(articles.router, prefix=API)
app.include_router(overlay.router, prefix=API)
app.include_router(library.router, prefix=API)
app.include_router(sync.router, prefix=API)
app.include_router(backups.router, prefix=API)
app.include_router(tts.router, prefix=API)
app.include_router(chat.router, prefix=API)
app.include_router(school.router, prefix=API)
app.include_router(junior_jobs.router, prefix=API)
app.include_router(stt.router, prefix=API)
app.include_router(calendar.router, prefix=API)


# Logged-out browsers opening these paths used to get the SPA shell and hang on
# "Opening your library…". Send them to sign-in instead. Not Junior chat.
APP_SHELL_ALIASES = frozenset({"archive", "library", "app", "home", "chat", "junior"})


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


def health_payload() -> dict[str, str]:
    body = {"status": "ok", **_build_info()}
    snap = rss.last_fetch_snapshot()
    if snap:
        if snap.get("status") is not None:
            body["rss_status"] = str(snap["status"])
        body["rss_bytes"] = str(int(snap.get("bytes") or 0))
        body["rss_item_count"] = str(int(snap.get("item_count") or 0))
    return body


def is_app_shell_alias(full_path: str) -> bool:
    first = (full_path or "").strip("/").split("/", 1)[0].lower()
    return first in APP_SHELL_ALIASES


def about_html() -> str:
    info = health_payload()
    build = info.get("build") or "unknown"
    built_at = info.get("built_at") or ""
    stamp = f" · {built_at}" if built_at else ""
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'/>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'/>"
        "<title>About StoryKeep</title></head><body>"
        "<main style='font-family:system-ui,sans-serif;max-width:36rem;margin:3rem auto;padding:0 1.25rem'>"
        "<h1>StoryKeep</h1>"
        "<p>A personal RSS reader and article archive. Sign in to open your library.</p>"
        f"<p>Build <strong>{build}</strong>{stamp}</p>"
        "<p><a href='/login'>Sign in</a></p>"
        "</main></body></html>"
    )


def _health() -> dict[str, str]:
    return health_payload()


def _static_headers(path: Path) -> dict[str, str]:
    suffix = path.suffix.lower()
    if suffix in {".html", ".js", ".css"}:
        return {"Cache-Control": "no-store"}
    return {"Cache-Control": "public, max-age=3600"}


def _about_page():
    directory = Path(settings.frontend_dir) if settings.frontend_dir else None
    if directory and directory.is_dir():
        nested = directory / "about" / "index.html"
        if nested.is_file():
            return FileResponse(nested, headers=_static_headers(nested))
        html_file = directory / "about.html"
        if html_file.is_file():
            return FileResponse(html_file, headers=_static_headers(html_file))
    return HTMLResponse(about_html())


def _login_redirect() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=302)


app.add_api_route("/health", _health, methods=["GET", "HEAD"], tags=["health"])
app.add_api_route("/api/health", _health, methods=["GET", "HEAD"], tags=["health"])
app.add_api_route("/about", _about_page, methods=["GET", "HEAD"], tags=["health"], include_in_schema=False)
for _alias in sorted(APP_SHELL_ALIASES):
    app.add_api_route(f"/{_alias}", _login_redirect, methods=["GET", "HEAD"], include_in_schema=False)
    app.add_api_route(f"/{_alias}/{{rest:path}}", _login_redirect, methods=["GET", "HEAD"], include_in_schema=False)


def _register_frontend(app: FastAPI) -> None:
    directory = Path(settings.frontend_dir) if settings.frontend_dir else None
    if not directory or not directory.is_dir():
        return

    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"])
    def frontend_page(full_path: str):
        if is_app_shell_alias(full_path):
            return RedirectResponse(url="/login", status_code=302)
        if full_path in {"api", "health", "about"} or full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
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
