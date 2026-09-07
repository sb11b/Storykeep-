from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Archive, Article
from app.services import extractor


def snapshot_article(db: Session, article: Article, archive_type: str = "html") -> Archive:
    html = article.content_html
    text = article.content_text
    if not html or not text:
        extractor.fill_article(db, article, force=True)
        html = article.content_html
        text = article.content_text
    payload = html or text or article.summary or article.url
    digest = hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()
    existing = next((row for row in article.archives if row.checksum == digest), None)
    if existing:
        return existing
    row = Archive(
        article_id=article.id,
        archive_type="readability" if archive_type == "html" else archive_type,
        content=payload,
        storage_backend="db",
        checksum=digest,
        byte_size=len(payload.encode("utf-8", errors="ignore")),
    )
    if not article.is_saved:
        article.is_saved = True
        article.saved_at = datetime.now(timezone.utc)
    db.add(row)
    db.add(article)
    db.flush()
    return row
