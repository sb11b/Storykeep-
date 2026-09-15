from collections.abc import Generator
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# Local Compose hostname `db` and Railway private DNS do not use the public proxy cert.
_NO_TLS_HOSTS = {"127.0.0.1", "localhost", "::1", "db"}

# Postgres waits on a row lock forever by default. One leaked transaction then
# freezes every later writer, and a writer on the event loop freezes the worker.
LOCK_TIMEOUT_MS = 8_000
STATEMENT_TIMEOUT_MS = 60_000
IDLE_IN_TRANSACTION_TIMEOUT_MS = 300_000
SESSION_TIMEOUT_OPTIONS = (
    f"-c lock_timeout={LOCK_TIMEOUT_MS}"
    f" -c statement_timeout={STATEMENT_TIMEOUT_MS}"
    f" -c idle_in_transaction_session_timeout={IDLE_IN_TRANSACTION_TIMEOUT_MS}"
)


@dataclass(frozen=True)
class DatabaseConnect:
    url: URL
    connect_args: dict[str, str]
    host: str
    port: int
    user: str
    password: str
    database: str


def _wants_proxy_tls(host: str) -> bool:
    lowered = (host or "").lower()
    if lowered in _NO_TLS_HOSTS:
        return False
    if lowered.endswith(".railway.internal"):
        return False
    return True


def parse_database_url(raw: str) -> DatabaseConnect:
    """Connect from host/user/password/database fields, never the raw URL.

    Railway's public Postgres URL often includes sslmode=verify-full (or a
    proxy cert that is not in the default CA store). Passing that string into
    the engine inherits those SSL settings and the handshake fails.

    We drop query-string SSL options and, for public hosts, encrypt with
    sslmode=require (no CA verify — same idea as ssl: { rejectUnauthorized: false }).

    Do not set NODE_TLS_REJECT_UNAUTHORIZED=0. That is a last-resort Node
    workaround that disables TLS for the whole process. This connect config
    is the supported fix. The Next.js UI never opens Postgres itself.
    """
    normalized = (raw or "").strip().replace("postgres://", "postgresql://", 1)
    normalized = normalized.replace("postgresql+psycopg2://", "postgresql://", 1)
    parsed = urlparse(normalized)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5432
    user = unquote(parsed.username) if parsed.username else ""
    password = unquote(parsed.password) if parsed.password else ""
    database = unquote((parsed.path or "/storykeep").lstrip("/") or "storykeep")
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=user or None,
        password=password or None,
        host=host,
        port=port,
        database=database,
    )
    connect_args: dict[str, str] = {"options": SESSION_TIMEOUT_OPTIONS}
    if _wants_proxy_tls(host):
        connect_args["sslmode"] = "require"
    return DatabaseConnect(
        url=url,
        connect_args=connect_args,
        host=host,
        port=port,
        user=user or "storykeep",
        password=password,
        database=database,
    )


db_connect = parse_database_url(settings.database_url)
engine = create_engine(db_connect.url, connect_args=db_connect.connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
