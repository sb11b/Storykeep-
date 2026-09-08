from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.sql import ColumnElement

from app.models import Article, Feed, User

DESTINATIONS = ("vault", "additions", "books", "notes", "schoolwork")
DEFAULT_DESTINATION = "additions"


def normalize_destination(value: str | None) -> str:
    raw = (value or DEFAULT_DESTINATION).strip().lower()
    if raw not in DESTINATIONS:
        raise ValueError("Destination must be Vault, Additions, Books, Notes, or Schoolwork.")
    return raw


def is_composed_guid(guid: str | None) -> bool:
    return (guid or "").startswith("storykeep-note:")


def composed_clause() -> ColumnElement[bool]:
    return Article.guid.startswith("storykeep-note:")


def effective_destination(article: Article) -> str | None:
    if not is_composed_guid(article.guid):
        return None
    dest = getattr(article, "destination", None)
    if dest in DESTINATIONS:
        return dest
    if (getattr(article, "source_kind", None) or "") == "textbook":
        return "books"
    return DEFAULT_DESTINATION


def source_kind_for_destination(destination: str) -> str:
    return "textbook" if destination == "books" else "obsidian"


def apply_destination(article: Article, destination: str, is_correction: bool | None = None) -> None:
    dest = normalize_destination(destination)
    article.destination = dest
    article.source_kind = source_kind_for_destination(dest)
    if is_correction is not None:
        article.is_correction = bool(is_correction)


def shelf_where(shelf: str) -> ColumnElement[bool] | None:
    composed = composed_clause()
    dest = func.coalesce(Article.destination, DEFAULT_DESTINATION)
    if shelf == "vault":
        imported = and_(Article.guid.startswith("obsidian:"), Article.source_kind != "textbook")
        return or_(imported, and_(composed, dest == "vault"))
    if shelf == "additions":
        return and_(composed, dest == "additions")
    if shelf == "books":
        imported_book = and_(Article.source_kind == "textbook", ~composed)
        return or_(imported_book, and_(composed, dest == "books"))
    if shelf == "notes":
        return and_(composed, dest == "notes")
    if shelf == "schoolwork":
        return and_(composed, dest == "schoolwork")
    return None


def apply_shelf_filter(stmt, shelf: str | None):
    if not shelf:
        return stmt
    clause = shelf_where(shelf)
    if clause is None:
        return stmt
    return stmt.where(clause)


def shelf_count(db, user: User, shelf: str) -> int:
    stmt = apply_shelf_filter(select(Article).join(Feed).where(Feed.user_id == user.id), shelf)
    return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
