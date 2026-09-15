from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, Feed, OverlayAddition, Tag, User
from app.services import changelog
from app.services.destination import (
    DEFAULT_DESTINATION,
    apply_destination,
    is_composed_guid,
    normalize_destination,
    source_kind_for_destination,
)
from app.services.markdown_html import markdown_to_html
_UNSET = object()

from app.services.vault_paths import (
    classify_zip_entry,
    import_tags_for_path,
    overlay_relpath,
    parse_hashtags,
    source_kind_for_path,
    title_from_path,
)

VAULT_FEED_URL = "https://storykeep.local/obsidian-vault"
MAX_VAULT_ZIP_BYTES = 100 * 1024 * 1024
MAX_NOTE_BYTES = 1_500_000


def vault_feed(db: Session, user: User) -> Feed:
    feed = db.scalar(select(Feed).where(Feed.user_id == user.id, Feed.url == VAULT_FEED_URL))
    if feed:
        return feed
    feed = Feed(
        user_id=user.id,
        url=VAULT_FEED_URL,
        title="Steve's Surface Vault",
        site_url=None,
        is_active=False,
    )
    db.add(feed)
    db.flush()
    changelog.record(db, user.id, "feed", feed.id, "upsert", {"url": VAULT_FEED_URL})
    return feed


def ensure_tag(db: Session, user: User, name: str) -> Tag:
    label = name.strip()[:40]
    tag = db.scalar(select(Tag).where(Tag.user_id == user.id, Tag.name == label))
    if tag:
        return tag
    tag = Tag(user_id=user.id, name=label)
    db.add(tag)
    db.flush()
    return tag


def import_obsidian_zip(db: Session, user: User, payload: bytes) -> dict[str, int | list[str]]:
    try:
        archive = ZipFile(BytesIO(payload))
    except BadZipFile as exc:
        raise ValueError("That file is not a zip archive.") from exc

    feed = vault_feed(db, user)
    imported = 0
    updated = 0
    skipped = 0
    attachments = 0
    errors: list[str] = []
    now = datetime.now(timezone.utc)

    for info in archive.infolist():
        try:
            kind, rel = classify_zip_entry(info.filename)
            if kind == "skip" or not rel:
                skipped += 1
                continue
            if kind == "image":
                attachments += 1
                continue
            raw = archive.read(info)
            if len(raw) > MAX_NOTE_BYTES:
                errors.append(f"{rel}: skipped (too large)")
                continue
            text = raw.decode("utf-8", errors="replace").replace("\x00", "")
            kind = source_kind_for_path(rel)
            title = _title_from_markdown(text) or title_from_path(rel)
            html = markdown_to_html(text)
            guid = f"obsidian:{rel}"[:2000]
            article = db.scalar(select(Article).where(Article.feed_id == feed.id, Article.guid == guid))
            if not article:
                article = db.scalar(
                    select(Article).where(Article.feed_id == feed.id, Article.obsidian_path == rel)
                )
            created = False
            if not article:
                article = Article(
                    feed_id=feed.id,
                    guid=guid,
                    url=f"obsidian://{rel}"[:4000],
                    title=title[:500],
                    content_text=text,
                    content_html=html,
                    published_at=now,
                    fetched_at=now,
                    is_saved=True,
                    saved_at=now,
                    source_kind=kind,
                    source_ref=rel,
                    obsidian_path=rel,
                )
                db.add(article)
                db.flush()
                created = True
            else:
                article.title = title[:500]
                article.content_text = text
                article.content_html = html
                article.guid = guid
                article.source_kind = kind
                article.source_ref = rel
                article.obsidian_path = rel
                article.fetched_at = now
                db.add(article)
            names = set(import_tags_for_path(rel))
            names.update(parse_hashtags(text))
            for name in names:
                tag = ensure_tag(db, user, name)
                if tag not in article.tags:
                    article.tags.append(tag)
            changelog.record(
                db,
                user.id,
                "article",
                article.id,
                "upsert",
                {"source_ref": rel, "imported": created},
            )
            if created:
                imported += 1
            else:
                updated += 1
            if (imported + updated) % 40 == 0:
                db.commit()
        except Exception as exc:
            errors.append(f"{info.filename}: {str(exc)[:180]}")
            db.rollback()
            feed = vault_feed(db, user)

    db.commit()
    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "attachments": attachments,
        "errors": errors[:40],
    }


def _title_from_markdown(text: str) -> str | None:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()[:500]
        if stripped:
            return None
    return None


def find_composed_note(
    db: Session,
    user: User,
    title: str,
    destination: str,
    folder_id=None,
) -> Article | None:
    heading = (title or "").strip()[:500]
    dest = (destination or "").strip().lower()
    if not heading or not dest:
        return None
    stmt = (
        select(Article)
        .join(Feed)
        .where(
            Feed.user_id == user.id,
            Article.guid.startswith("storykeep-note:"),
            Article.title == heading,
            Article.destination == dest,
        )
        .order_by(Article.updated_at.desc())
    )
    if folder_id:
        stmt = stmt.where(Article.folder_id == folder_id)
    else:
        stmt = stmt.where(Article.folder_id.is_(None))
    return db.scalars(stmt).first()


def create_composed_note(
    db: Session,
    user: User,
    title: str,
    markdown: str,
    tags: list[str] | None = None,
    destination: str | None = None,
    folder_id=None,
    parent_id=None,
    is_correction: bool = False,
) -> Article:
    """StoryKeep-owned note: readable article + overlay addition. Never writes vault originals."""
    heading = (title or "").strip()
    body = (markdown or "").strip()
    if not heading or not body:
        raise ValueError("Title and body are required.")
    if len(body.encode("utf-8")) > MAX_NOTE_BYTES:
        raise ValueError("That note is larger than 1.5 MB.")
    dest = normalize_destination(destination, user)
    from app.services.folders import resolve_folder_id

    resolved_folder_id = resolve_folder_id(db, user, dest, folder_id)
    tags_l = [(tag or "").lower() for tag in tags or []]
    if dest == DEFAULT_DESTINATION and (heading.startswith("_book_") or "book" in tags_l):
        dest = "books"
    existing = find_composed_note(db, user, heading, dest, resolved_folder_id)
    if existing:
        return update_composed_note(
            db,
            user,
            existing,
            heading,
            body,
            is_correction,
            destination=dest,
            folder_id=resolved_folder_id,
        )
    now = datetime.now(timezone.utc)
    feed = vault_feed(db, user)
    kind = source_kind_for_destination(dest)
    note_id = uuid4()
    article = Article(
        id=note_id,
        feed_id=feed.id,
        guid=f"storykeep-note:{note_id}",
        url="storykeep://pending",
        title=heading[:500],
        summary=body[:280],
        content_text=body,
        content_html=markdown_to_html(body),
        published_at=now,
        fetched_at=now,
        is_read=True,
        read_at=now,
        is_saved=True,
        saved_at=now,
        source_kind=kind,
        parent_id=parent_id,
        destination=dest,
        folder_id=resolved_folder_id,
        is_correction=bool(is_correction),
    )
    db.add(article)
    db.flush()
    pack_kind = "correction" if article.is_correction else "addition"
    article.source_ref = overlay_relpath(pack_kind, None, f"{heading}-{str(article.id)[:8]}")
    article.url = f"storykeep://{article.source_ref}"[:4000]
    addition = OverlayAddition(
        user_id=user.id,
        article_id=article.id,
        title=heading[:200],
        markdown=body,
        destination=dest,
        is_correction=bool(is_correction),
    )
    db.add(addition)
    db.flush()
    names = set(parse_hashtags(body))
    for raw in tags or []:
        label = raw.strip()[:40]
        if label:
            names.add(label)
    for name in names:
        tag = ensure_tag(db, user, name)
        if tag not in article.tags:
            article.tags.append(tag)
    changelog.record(db, user.id, "article", article.id, "upsert", {"composed": True, "source_ref": article.source_ref, "destination": dest, "folder_id": str(resolved_folder_id) if resolved_folder_id else None})
    changelog.record(db, user.id, "addition", addition.id, "upsert", {"article_id": str(article.id), "composed": True, "destination": dest})
    db.commit()
    return article


def is_composed_note(article: Article) -> bool:
    return is_composed_guid(article.guid)


def update_composed_note(
    db: Session,
    user: User,
    article: Article,
    title: str,
    markdown: str,
    is_correction: bool | None = None,
    folder_id=_UNSET,
    destination=_UNSET,
    *,
    commit: bool = True,
    confirm_short: bool = False,
    snapshot: bool = True,
) -> Article:
    """Edit a StoryKeep-authored note. Imported vault files stay read-only."""
    if not is_composed_note(article):
        raise ValueError("Imported vault notes stay read-only. Save a correction or an addition instead.")
    heading = (title or "").strip()
    body = (markdown or "").strip()
    if not heading or not body:
        raise ValueError("Title and body are required.")
    if len(body.encode("utf-8")) > MAX_NOTE_BYTES:
        raise ValueError("That note is larger than 1.5 MB.")
    if snapshot:
        from app.services.note_revisions import NoteShrinkBlocked, snapshot_before_save

        snapshot_before_save(db, user, article, body, confirm_short=confirm_short)
    now = datetime.now(timezone.utc)
    dest = getattr(article, "destination", None) or DEFAULT_DESTINATION
    if destination is not _UNSET and destination:
        dest = normalize_destination(destination, user)
        apply_destination(article, dest, None, user)
    if is_correction is not None:
        article.is_correction = bool(is_correction)
        article.source_kind = source_kind_for_destination(dest)
    if folder_id is not _UNSET:
        from app.services.folders import resolve_folder_id

        if folder_id is None:
            article.folder_id = None
        else:
            article.folder_id = resolve_folder_id(db, user, dest, folder_id)
    article.title = heading[:500]
    article.summary = body[:280]
    article.content_text = body
    article.content_html = markdown_to_html(body)
    article.updated_at = now
    addition = db.scalar(
        select(OverlayAddition)
        .where(OverlayAddition.user_id == user.id, OverlayAddition.article_id == article.id)
        .order_by(OverlayAddition.created_at.asc())
    )
    if addition:
        addition.title = heading[:200]
        addition.markdown = body
        addition.destination = dest
        addition.updated_at = now
        addition.is_correction = bool(getattr(article, "is_correction", False))
    else:
        addition = OverlayAddition(
            user_id=user.id,
            article_id=article.id,
            title=heading[:200],
            markdown=body,
            destination=getattr(article, "destination", None) or DEFAULT_DESTINATION,
            is_correction=bool(getattr(article, "is_correction", False)),
        )
        db.add(addition)
        db.flush()
    changelog.record(db, user.id, "article", article.id, "upsert", {"composed": True, "edited": True})
    changelog.record(db, user.id, "addition", addition.id, "upsert", {"article_id": str(article.id), "edited": True})
    if commit:
        db.commit()
    else:
        db.flush()
    return article


def set_composed_destination(
    db: Session,
    user: User,
    article: Article,
    destination: str,
    is_correction: bool | None = None,
    folder_id=_UNSET,
    *,
    commit: bool = True,
) -> Article:
    """Move a StoryKeep note to another shelf. Does not duplicate or write vault originals."""
    if not is_composed_note(article):
        raise ValueError("Imported vault notes stay on Vault. File a StoryKeep note instead.")
    dest = normalize_destination(destination, user)
    flag = article.is_correction if is_correction is None else bool(is_correction)
    apply_destination(article, dest, flag, user)
    from app.services.folders import get_folder, match_folder_by_name, resolve_folder_id

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
    pack_kind = "correction" if article.is_correction else "addition"
    article.source_ref = overlay_relpath(pack_kind, None, f"{article.title}-{str(article.id)[:8]}")
    article.url = f"storykeep://{article.source_ref}"[:4000]
    article.updated_at = datetime.now(timezone.utc)
    addition = db.scalar(
        select(OverlayAddition)
        .where(OverlayAddition.user_id == user.id, OverlayAddition.article_id == article.id)
        .order_by(OverlayAddition.created_at.asc())
    )
    if addition:
        addition.destination = dest
        addition.is_correction = article.is_correction
        addition.updated_at = article.updated_at
    changelog.record(
        db,
        user.id,
        "article",
        article.id,
        "upsert",
        {"destination": dest, "is_correction": article.is_correction, "moved": True},
    )
    if commit:
        db.commit()
    else:
        db.flush()
    return article

