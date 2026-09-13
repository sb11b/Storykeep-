from __future__ import annotations

from sqlalchemy import and_, func, or_, select
from sqlalchemy.sql import ColumnElement

from app.models import Article, Feed, User
from app.services.custom_note_shelves import is_custom_note_shelf

DESTINATIONS = ("vault", "additions", "books", "notes", "schoolwork")
FOLDER_SHELVES = DESTINATIONS
DEFAULT_DESTINATION = "additions"


def normalize_destination(value: str | None, user: User | None = None) -> str:
    raw = (value or DEFAULT_DESTINATION).strip().lower()
    if raw in DESTINATIONS:
        return raw
    if user and is_custom_note_shelf(user, raw):
        return raw
    raise ValueError("Destination must be Vault, Additions, Books, Notes, Schoolwork, or a custom shelf.")


def is_composed_guid(guid: str | None) -> bool:
    return (guid or "").startswith("storykeep-note:")


def is_imported_vault_note(article: Article) -> bool:
    return (article.guid or "").startswith("obsidian:") and (getattr(article, "source_kind", None) or "") != "textbook"


def is_imported_textbook(article: Article) -> bool:
    return (getattr(article, "source_kind", None) or "") == "textbook" and not is_composed_guid(article.guid)


def explicitly_filed_on(shelf: str) -> ColumnElement[bool]:
    return Article.destination == shelf


def composed_clause() -> ColumnElement[bool]:
    return Article.guid.startswith("storykeep-note:")


def effective_destination(article: Article) -> str | None:
    dest = getattr(article, "destination", None)
    if dest in DESTINATIONS:
        return dest
    if not is_composed_guid(article.guid):
        if is_imported_textbook(article):
            return "books"
        return None
    if (getattr(article, "source_kind", None) or "") == "textbook":
        return "books"
    return DEFAULT_DESTINATION


def source_kind_for_destination(destination: str) -> str:
    return "textbook" if destination == "books" else "obsidian"


def apply_destination(
    article: Article, destination: str, is_correction: bool | None = None, user: User | None = None
) -> None:
    dest = normalize_destination(destination, user)
    article.destination = dest
    article.source_kind = source_kind_for_destination(dest)
    if is_correction is not None:
        article.is_correction = bool(is_correction)


def shelf_where(shelf: str) -> ColumnElement[bool] | None:
    composed = composed_clause()
    dest = func.coalesce(Article.destination, DEFAULT_DESTINATION)
    filed = explicitly_filed_on(shelf)
    if shelf == "vault":
        imported = and_(Article.guid.startswith("obsidian:"), Article.source_kind != "textbook")
        return or_(imported, and_(composed, dest == "vault"), filed)
    if shelf == "additions":
        return or_(and_(composed, dest == "additions"), filed)
    if shelf == "books":
        imported_book = and_(
            Article.source_kind == "textbook",
            ~composed,
            Article.destination.is_(None),
        )
        return or_(imported_book, and_(composed, dest == "books"), filed)
    if shelf == "notes":
        return or_(and_(composed, dest == "notes"), filed)
    if shelf == "schoolwork":
        return or_(and_(composed, dest == "schoolwork"), filed)
    return or_(and_(composed, dest == shelf), filed)


def apply_shelf_filter(stmt, shelf: str | None):
    if not shelf:
        return stmt
    clause = shelf_where(shelf)
    return stmt.where(clause)


def shelf_count(db, user: User, shelf: str) -> int:
    stmt = apply_shelf_filter(select(Article).join(Feed).where(Feed.user_id == user.id), shelf)
    return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
