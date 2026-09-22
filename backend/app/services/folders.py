from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Article, Feed, Folder, User
from app.services.custom_note_shelves import is_custom_note_shelf
from app.services.destination import FOLDER_SHELVES, apply_shelf_filter, normalize_destination

FOLDER_SHELF_SET = set(FOLDER_SHELVES)


def normalize_folder_shelf(shelf: str, user: User | None = None) -> str:
    raw = (shelf or "").strip().lower()
    if raw in FOLDER_SHELF_SET:
        return raw
    if user and is_custom_note_shelf(user, raw):
        return raw
    raise ValueError("Folder shelf must be Vault, Additions, Books, Notes, Schoolwork, or a custom shelf.")


def normalize_folder_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned:
        raise ValueError("Folder name is required.")
    if len(cleaned) > 80:
        raise ValueError("Folder name must be 80 characters or fewer.")
    return cleaned


def get_folder(db: Session, user: User, folder_id: UUID) -> Folder | None:
    row = db.scalar(select(Folder).where(Folder.id == folder_id, Folder.user_id == user.id))
    return row


def folder_item_count(db: Session, user: User, folder: Folder) -> int:
    stmt = apply_shelf_filter(
        select(Article)
        .join(Feed)
        .where(Feed.user_id == user.id, Article.folder_id == folder.id),
        folder.shelf,
    )
    return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0


def list_folders(db: Session, user: User, shelf: str | None = None) -> list[tuple[Folder, int]]:
    stmt = select(Folder).where(Folder.user_id == user.id)
    if shelf:
        stmt = stmt.where(Folder.shelf == normalize_folder_shelf(shelf, user))
    rows = db.scalars(stmt.order_by(Folder.pinned.desc(), Folder.shelf.asc(), Folder.name.asc())).all()
    return [(row, folder_item_count(db, user, row)) for row in rows]


def ensure_folder_on_shelf(db: Session, user: User, shelf: str, name: str, *, commit: bool = False) -> Folder:
    """Return the folder named `name` on this shelf, creating it if needed. Never reuse another shelf."""
    shelf_norm = normalize_folder_shelf(shelf, user)
    label = normalize_folder_name(name)
    existing = db.scalar(
        select(Folder).where(Folder.user_id == user.id, Folder.shelf == shelf_norm, Folder.name == label)
    )
    if existing:
        return existing
    row = Folder(user_id=user.id, shelf=shelf_norm, name=label)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError as exc:
        raced = db.scalar(
            select(Folder).where(Folder.user_id == user.id, Folder.shelf == shelf_norm, Folder.name == label)
        )
        if raced:
            return raced
        raise ValueError("Could not create that folder on this shelf.") from exc
    if commit:
        db.commit()
        db.refresh(row)
    return row


def create_folder(db: Session, user: User, shelf: str, name: str) -> Folder:
    return ensure_folder_on_shelf(db, user, shelf, name, commit=True)


def set_folder_pinned(db: Session, user: User, folder_id: UUID, pinned: bool) -> Folder:
    row = get_folder(db, user, folder_id)
    if not row:
        raise ValueError("Folder not found.")
    row.pinned = pinned
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def rename_folder(db: Session, user: User, folder_id: UUID, name: str) -> Folder:
    row = get_folder(db, user, folder_id)
    if not row:
        raise ValueError("Folder not found.")
    label = normalize_folder_name(name)
    conflict = db.scalar(
        select(Folder).where(
            Folder.user_id == user.id,
            Folder.shelf == row.shelf,
            Folder.name == label,
            Folder.id != row.id,
        )
    )
    if conflict:
        raise ValueError("A folder with that name already exists on this shelf.")
    row.name = label
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_folder(db: Session, user: User, folder_id: UUID) -> None:
    row = get_folder(db, user, folder_id)
    if not row:
        raise ValueError("Folder not found.")
    articles = db.scalars(select(Article).where(Article.folder_id == row.id)).all()
    for article in articles:
        article.folder_id = None
        db.add(article)
    db.delete(row)
    db.commit()


def resolve_folder_id(db: Session, user: User, destination: str, folder_id: UUID | None) -> UUID | None:
    if folder_id is None:
        return None
    row = get_folder(db, user, folder_id)
    if not row:
        raise ValueError("Folder not found.")
    dest = normalize_destination(destination, user)
    if row.shelf == dest:
        return row.id
    # Folder is on another shelf. Do not move the note; use or create the same name here.
    return ensure_folder_on_shelf(db, user, dest, row.name, commit=False).id


def match_folder_by_name(db: Session, user: User, shelf: str, name: str | None) -> UUID | None:
    if not name:
        return None
    row = db.scalar(
        select(Folder).where(Folder.user_id == user.id, Folder.shelf == shelf, Folder.name == name)
    )
    return row.id if row else None


def folder_name_for_article(db: Session, user: User, article: Article) -> str | None:
    folder_id = getattr(article, "folder_id", None)
    if not folder_id:
        return None
    row = get_folder(db, user, folder_id)
    return row.name if row else None


def apply_folder_filter(stmt, folder_id: UUID | None):
    if folder_id:
        return stmt.where(Article.folder_id == folder_id)
    return stmt
