from collections.abc import Generator
from urllib.parse import unquote, urlparse

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def parse_database_url(raw: str) -> tuple[URL, dict[str, str]]:
    """Build a SQLAlchemy URL from fields only — never reuse the raw string.

    Railway's public Postgres proxy presents a cert that is not in the default
    CA store. Passing the original URL (or its sslmode query) lets the driver
    inherit verify-full behavior. We drop query/ssl settings from the URL and
    attach encrypt-without-verify for remote hosts.

    Do not set NODE_TLS_REJECT_UNAUTHORIZED=0. That is a last-resort Node
    workaround that disables TLS checks for the whole process. This pool
    config is the supported fix.
    """
    normalized = (raw or "").strip().replace("postgres://", "postgresql://", 1)
    normalized = normalized.replace("postgresql+psycopg2://", "postgresql://", 1)
    parsed = urlparse(normalized)
    host = parsed.hostname or "127.0.0.1"
    database = unquote((parsed.path or "/storykeep").lstrip("/") or "storykeep")
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=unquote(parsed.username) if parsed.username else None,
        password=unquote(parsed.password) if parsed.password else None,
        host=host,
        port=parsed.port or 5432,
        database=database,
    )
    connect_args: dict[str, str] = {}
    if host not in _LOCAL_HOSTS:
        # Encrypt the session. sslmode=require does not verify the proxy CA
        # (same idea as pg Pool ssl: { rejectUnauthorized: false }).
        connect_args["sslmode"] = "require"
    return url, connect_args


_url, _connect_args = parse_database_url(settings.database_url)
engine = create_engine(_url, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
