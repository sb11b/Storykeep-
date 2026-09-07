from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, Feed, Tag, User
from app.services import changelog
from app.services.markdown_html import markdown_to_html
from app.services.vault_paths import (
    classify_zip_entry,
    import_tags_for_path,
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
