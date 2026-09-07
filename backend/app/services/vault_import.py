from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, Feed, OverlayAddition, Tag, User
from app.services import changelog
from app.services.markdown_html import markdown_to_html
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


def create_composed_note(db: Session, user: User, title: str, markdown: str, tags: list[str] | None = None) -> Article:
    """StoryKeep-owned note: readable article + overlay addition. Never writes vault originals."""
    heading = (title or "").strip()
    body = (markdown or "").strip()
    if not heading or not body:
        raise ValueError("Title and body are required.")
    if len(body.encode("utf-8")) > MAX_NOTE_BYTES:
        raise ValueError("That note is larger than 1.5 MB.")
    now = datetime.now(timezone.utc)
    feed = vault_feed(db, user)
    kind = "textbook" if heading.startswith("_book_") or any((tag or "").lower() == "book" for tag in tags or []) else "obsidian"
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
        is_saved=True,
        saved_at=now,
        source_kind=kind,
    )
    db.add(article)
    db.flush()
    article.source_ref = overlay_relpath("addition", None, f"{heading}-{str(article.id)[:8]}")
    article.url = f"storykeep://{article.source_ref}"[:4000]
    addition = OverlayAddition(
        user_id=user.id,
        article_id=article.id,
        title=heading[:200],
        markdown=body,
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
    changelog.record(db, user.id, "article", article.id, "upsert", {"composed": True, "source_ref": article.source_ref})
    changelog.record(db, user.id, "addition", addition.id, "upsert", {"article_id": str(article.id), "composed": True})
    db.commit()
    return article


def is_composed_note(article: Article) -> bool:
    guid = article.guid or ""
    ref = (article.source_ref or "").replace("\\", "/")
    return guid.startswith("storykeep-note:") or ref.startswith("StoryKeep/Additions/")


def update_composed_note(db: Session, user: User, article: Article, title: str, markdown: str) -> Article:
    """Edit a StoryKeep-authored note. Imported vault files stay read-only."""
    if not is_composed_note(article):
        raise ValueError("Imported vault notes stay read-only. Save a correction or an addition instead.")
    heading = (title or "").strip()
    body = (markdown or "").strip()
    if not heading or not body:
        raise ValueError("Title and body are required.")
    if len(body.encode("utf-8")) > MAX_NOTE_BYTES:
        raise ValueError("That note is larger than 1.5 MB.")
    now = datetime.now(timezone.utc)
    article.title = heading[:500]
    article.summary = body[:280]
    article.content_text = body
    article.content_html = markdown_to_html(body)
    addition = db.scalar(
        select(OverlayAddition)
        .where(OverlayAddition.user_id == user.id, OverlayAddition.article_id == article.id)
        .order_by(OverlayAddition.created_at.asc())
    )
    if addition:
        addition.title = heading[:200]
        addition.markdown = body
        addition.updated_at = now
    else:
        addition = OverlayAddition(
            user_id=user.id,
            article_id=article.id,
            title=heading[:200],
            markdown=body,
        )
        db.add(addition)
        db.flush()
    changelog.record(db, user.id, "article", article.id, "upsert", {"composed": True, "edited": True})
    changelog.record(db, user.id, "addition", addition.id, "upsert", {"article_id": str(article.id), "edited": True})
    db.commit()
    return article
