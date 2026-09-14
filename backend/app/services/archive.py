from __future__ import annotations

import hashlib
import html as html_lib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session
from weasyprint import HTML as WeasyHTML

from app.config import settings
from app.models import Archive, Article
from app.services import extractor
from app.services.backup import object_store_ready, upload_object_file

logger = logging.getLogger(__name__)
_HTTP_URL = re.compile(r"^https?://", re.I)
PDF_SNAPSHOT_TYPES = {"pdf"}
PDF_RENDERER = "weasyprint"

_PDF_PAGE_CSS = """
@page { size: letter; margin: 0.85in; }
html, body {
  font-family: "DejaVu Sans", "Noto Sans", sans-serif;
  font-size: 12pt;
  line-height: 1.45;
  color: #111;
  width: 6.8in;
}
h1 { font-size: 20pt; font-weight: 700; margin: 0 0 14pt; line-height: 1.25; }
h2 { font-size: 16pt; font-weight: 700; margin: 16pt 0 10pt; line-height: 1.3; }
h3 { font-size: 13pt; font-weight: 700; margin: 14pt 0 8pt; line-height: 1.3; }
p { margin: 0 0 10pt; }
ul, ol { margin: 0 0 10pt; padding-left: 22pt; }
li { margin: 0 0 6pt; }
br { display: block; margin: 0 0 4pt; content: ""; }
blockquote { margin: 0 0 10pt; padding-left: 12pt; }
img { max-width: 100%; }
"""


def pdf_snapshot_path(article_id: UUID, archive_id: UUID) -> Path:
    folder = settings.archive_dir / str(article_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{archive_id}.pdf"


def article_html_for_pdf(article: Article) -> str:
    """Sanitized article HTML for PDF layout. Does not mutate the article."""
    raw = (getattr(article, "content_html", None) or "").strip()
    if raw:
        return extractor._sanitize_html(raw)
    text = (getattr(article, "content_text", None) or getattr(article, "summary", None) or "").strip()
    if not text:
        return ""
    blocks = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()] or [text]
    pieces = [f"<p>{html_lib.escape(block).replace(chr(10), '<br/>')}</p>" for block in blocks]
    return extractor._sanitize_html("".join(pieces))


def render_article_pdf(title: str, html: str) -> bytes:
    """Print sanitized article HTML with block layout via WeasyPrint."""
    heading = html_lib.escape(title or "Untitled")
    body = (html or "").strip() or "<p></p>"
    document = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'/>"
        f"<style>{_PDF_PAGE_CSS}</style></head><body>"
        f"<h1>{heading}</h1>{body}</body></html>"
    )
    payload = WeasyHTML(string=document, base_url=".").write_pdf()
    if not payload or not payload.startswith(b"%PDF"):
        raise RuntimeError("WeasyPrint did not produce a PDF")
    return payload


def snapshot_article(db: Session, article: Article, archive_type: str = "html") -> Archive | None:
    kind = (archive_type or "html").strip().lower()
    if kind in PDF_SNAPSHOT_TYPES:
        return _snapshot_pdf(db, article)
    return _snapshot_html(db, article, kind)


def _snapshot_html(db: Session, article: Article, archive_type: str) -> Archive | None:
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


def _snapshot_pdf(db: Session, article: Article) -> Archive | None:
    html = article_html_for_pdf(article)
    if not html.strip():
        logger.info("skip pdf snapshot for article %s: no storable body", article.id)
        return None
    payload = render_article_pdf(article.title or "Untitled", html)
    digest = hashlib.sha256(payload).hexdigest()
    existing = next(
        (row for row in (article.archives or []) if row.archive_type == "pdf" and row.checksum == digest),
        None,
    )
    if existing:
        return existing
    archive_id = uuid4()
    path = pdf_snapshot_path(article.id, archive_id)
    path.write_bytes(payload)
    backend = "local"
    if object_store_ready():
        try:
            prefix = settings.s3_prefix.strip("/")
            upload_object_file(path, f"{prefix}/pdf-snapshots/{archive_id}.pdf")
            backend = "s3"
        except Exception:
            logger.warning("PDF snapshot uploaded locally only; object store copy failed for %s", archive_id)
    row = Archive(
        id=archive_id,
        article_id=article.id,
        archive_type="pdf",
        content=None,
        storage_backend=backend,
        storage_path=str(path),
        checksum=digest,
        byte_size=len(payload),
    )
    if not article.is_saved:
        article.is_saved = True
        article.saved_at = datetime.now(timezone.utc)
    db.add(row)
    db.add(article)
    db.flush()
    return row


def restore_article_from_archive(db: Session, article: Article, row: Archive) -> None:
    """Apply a snapshot as the article's offline view.

    HTML: snapshot the current body first, then load the chosen snapshot
    through the extractor sanitizer. PDF: set offline_view=pdf only;
    content_html and content_text are not modified.
    """
    if getattr(row, "archive_type", None) == "pdf":
        path = Path(row.storage_path or "")
        if not path.is_file():
            raise FileNotFoundError("PDF snapshot file is missing")
        article.offline_view = "pdf"
        article.offline_archive_id = row.id
        db.add(article)
        db.flush()
        return

    snapshot_article(db, article, "html")
    raw = row.content or ""
    html = extractor._sanitize_html(raw) if raw.strip() else raw
    text = extractor._clean_text(extractor._strip_tags(html)) if html else ""
    article.content_html = html
    article.content_text = text or None
    article.offline_view = "html"
    article.offline_archive_id = row.id
    db.add(article)
