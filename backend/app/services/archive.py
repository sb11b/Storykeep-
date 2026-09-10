from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Archive, Article
from app.services import extractor

logger = logging.getLogger(__name__)
_HTTP_URL = re.compile(r"^https?://", re.I)


def snapshot_article(db: Session, article: Article, archive_type: str = "html") -> Archive | None:
    html = article.content_html
    text = article.content_text
    if (not html or not text) and _HTTP_URL.match((article.url or "").strip()):
        extractor.fill_article(db, article, force=True)[0]
        html = article.content_html
        text = article.content_text
    payload = html or text or article.summary or article.url or ""
    if not payload.strip():
        logger.info("skip snapshot for article %s: no storable body", article.id)
        return None
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
