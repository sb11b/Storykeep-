from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Article, User
from app.services import changelog
from app.services.destination import is_imported_vault_note, normalize_destination
from app.services.folders import get_folder, match_folder_by_name, resolve_folder_id
from app.services.vault_import import is_composed_note, set_composed_destination

_UNSET = object()


def set_article_filing(
    db: Session,
    user: User,
    article: Article,
    destination: str | None,
    folder_id=_UNSET,
    is_correction: bool | None = None,
    *,
    commit: bool = True,
) -> Article:
    """File any article onto a StoryKeep shelf + folder. Never writes Steve's Surface Vault."""
    if is_imported_vault_note(article):
        raise ValueError("Imported vault notes stay on Vault. They cannot be moved to another shelf.")

    if is_composed_note(article):
        if not destination:
            raise ValueError("StoryKeep notes must stay on a shelf.")
        return set_composed_destination(
            db,
            user,
            article,
            destination,
            is_correction,
            folder_id,
            commit=commit,
        )

    now = datetime.now(timezone.utc)
    if destination is None or str(destination).strip() == "":
        article.destination = None
        article.folder_id = None
    else:
        dest = normalize_destination(destination)
        article.destination = dest
        if folder_id is not _UNSET:
            if folder_id is None:
                article.folder_id = None
            else:
                article.folder_id = resolve_folder_id(db, user, dest, folder_id)
        else:
            previous_name = None
            if article.folder_id:
                previous = get_folder(db, user, article.folder_id)
                previous_name = previous.name if previous else None
            article.folder_id = match_folder_by_name(db, user, dest, previous_name)

    article.updated_at = now
    changelog.record(
        db,
        user.id,
        "article",
        article.id,
        "upsert",
        {
            "destination": article.destination,
            "folder_id": str(article.folder_id) if article.folder_id else None,
            "filed": True,
        },
    )
    db.add(article)
    if commit:
        db.commit()
    else:
        db.flush()
    return article
