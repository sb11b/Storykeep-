from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Archive, Article, Feed, User
from app.services import changelog
from app.services.file_extract import extract_document, suffix_of
from app.services.markdown_html import markdown_to_html
from app.services.vault_import import ensure_tag
from app.services.vault_paths import windows_safe_component

UPLOAD_FEED_URL = "https://storykeep.local/uploads"
MAX_UPLOAD_BYTES = 40 * 1024 * 1024


def upload_feed(db: Session, user: User) -> Feed:
    feed = db.scalar(select(Feed).where(Feed.user_id == user.id, Feed.url == UPLOAD_FEED_URL))
    if feed:
        return feed
    feed = Feed(
        user_id=user.id,
        url=UPLOAD_FEED_URL,
        title="Uploaded files",
        site_url=None,
        is_active=False,
    )
    db.add(feed)
    db.flush()
    changelog.record(db, user.id, "feed", feed.id, "upsert", {"url": UPLOAD_FEED_URL})
    return feed


def ingest_upload(
    db: Session,
    user: User,
    filename: str,
    payload: bytes,
    title: str | None = None,
    tags: list[str] | None = None,
) -> Article:
    if len(payload) > MAX_UPLOAD_BYTES:
        raise ValueError("That file is larger than 40 MB.")
    if not payload:
        raise ValueError("That file is empty.")
    guessed_title, text = extract_document(filename, payload)
    heading = (title or "").strip() or guessed_title
    if not text:
        text = "No extractable text was found. The original file is stored. If this is a scanned PDF, paste the text as a Vault note."
    now = datetime.now(timezone.utc)
    digest = hashlib.sha256(payload).hexdigest()
    feed = upload_feed(db, user)
    guid = f"file:{digest}"
    article = db.scalar(select(Article).where(Article.feed_id == feed.id, Article.guid == guid))
    html = markdown_to_html(text)
    if article:
        article.title = heading[:500]
        article.content_text = text
        article.content_html = html
        article.summary = text[:280]
        article.fetched_at = now
        article.is_saved = True
        article.saved_at = article.saved_at or now
        article.source_kind = "file"
        article.source_ref = Path(filename.replace("\\", "/")).name
        db.add(article)
    else:
        note_id = uuid4()
        original_name = Path(filename.replace("\\", "/")).name
        article = Article(
            id=note_id,
            feed_id=feed.id,
            guid=guid,
            url=f"storykeep://uploads/{original_name}"[:4000],
            title=heading[:500],
            summary=text[:280],
            content_text=text,
            content_html=html,
            published_at=now,
            fetched_at=now,
            is_saved=True,
            saved_at=now,
            source_kind="file",
            source_ref=original_name,
        )
        db.add(article)
        db.flush()
        stored = _store_original(user.id, article.id, original_name, payload)
        db.add(
            Archive(
                article_id=article.id,
                archive_type="original_file",
                content=original_name,
                storage_backend="disk",
                storage_path=str(stored),
                checksum=digest,
                byte_size=len(payload),
            )
        )
    names = {item.strip()[:40] for item in (tags or []) if item.strip()}
    for name in names:
        tag = ensure_tag(db, user, name)
        if tag not in article.tags:
            article.tags.append(tag)
    changelog.record(db, user.id, "article", article.id, "upsert", {"upload": True, "filename": article.source_ref})
    db.commit()
    return article


def original_file_path(article: Article) -> Path | None:
    for row in article.archives or []:
        if row.archive_type == "original_file" and row.storage_path:
            path = Path(row.storage_path)
            if path.is_file():
                return path
    return None


def _store_original(user_id, article_id, filename: str, payload: bytes) -> Path:
    folder = settings.data_dir / "uploads" / str(user_id) / str(article_id)
    folder.mkdir(parents=True, exist_ok=True)
    suffix = suffix_of(filename)
    stem = windows_safe_component(Path(filename).stem)
    path = folder / f"{stem}{suffix}"
    path.write_bytes(payload)
    return path
