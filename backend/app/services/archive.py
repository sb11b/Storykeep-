from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Archive, Article
from app.services import extractor
from app.services.backup import object_store_ready, upload_object_file

logger = logging.getLogger(__name__)
_HTTP_URL = re.compile(r"^https?://", re.I)
PDF_SNAPSHOT_TYPES = {"pdf"}


def pdf_snapshot_path(article_id: UUID, archive_id: UUID) -> Path:
    folder = settings.archive_dir / str(article_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{archive_id}.pdf"


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _latin1(text: str) -> str:
    return (text or "").encode("latin-1", "replace").decode("latin-1")


def _wrap_lines(text: str, width: int = 90) -> list[str]:
    lines: list[str] = []
    for paragraph in (text or "").splitlines() or [""]:
        safe = _latin1(paragraph)
        if not safe:
            lines.append("")
            continue
        while len(safe) > width:
            cut = safe.rfind(" ", 0, width)
            if cut < 20:
                cut = width
            lines.append(safe[:cut].rstrip())
            safe = safe[cut:].lstrip()
        lines.append(safe)
    return lines or [""]


def render_article_pdf(title: str, body: str) -> bytes:
    """Minimal PDF 1.4 of the stored article text. Helvetica / Latin-1."""
    heading = _wrap_lines(title or "Untitled", 80)
    body_lines = _wrap_lines(body or "", 90)
    lines = heading + [""] + body_lines
    per_page = 58
    page_chunks = [lines[index : index + per_page] for index in range(0, max(len(lines), 1), per_page)] or [[""]]

    content_streams: list[bytes] = []
    for page_lines in page_chunks:
        commands = ["BT", "/F1 11 Tf", "14 TL", "48 780 Td"]
        first = True
        for line in page_lines:
            if not first:
                commands.append("T*")
            first = False
            commands.append(f"({_pdf_escape(line)}) Tj")
        commands.append("ET")
        content_streams.append("\n".join(commands).encode("latin-1"))

    font_obj = 3
    page_count = len(content_streams)
    page_objs = list(range(4, 4 + page_count * 2, 2))
    content_objs = [num + 1 for num in page_objs]
    pages_obj = 2
    catalog_obj = 1

    body_objects: dict[int, bytes] = {
        catalog_obj: f"<< /Type /Catalog /Pages {pages_obj} 0 R >>".encode("latin-1"),
        pages_obj: (
            f"<< /Type /Pages /Count {page_count} /Kids [{' '.join(f'{n} 0 R' for n in page_objs)}] >>"
        ).encode("latin-1"),
        font_obj: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for page_obj, content_obj, stream in zip(page_objs, content_objs, content_streams):
        body_objects[page_obj] = (
            f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_obj} 0 R /Resources << /Font << /F1 {font_obj} 0 R >> >> >>"
        ).encode("latin-1")
        body_objects[content_obj] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1") + stream + b"\nendstream"
        )

    max_obj = max(body_objects)
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number in range(1, max_obj + 1):
        offsets.append(len(out))
        payload = body_objects[number]
        out.extend(f"{number} 0 obj\n".encode("latin-1"))
        out.extend(payload)
        out.extend(b"\nendobj\n")
    startxref = len(out)
    out.extend(f"xref\n0 {max_obj + 1}\n".encode("latin-1"))
    out.extend(b"0000000000 65535 f \n")
    for pos in offsets[1:]:
        out.extend(f"{pos:010d} 00000 n \n".encode("latin-1"))
    out.extend(
        f"trailer << /Size {max_obj + 1} /Root {catalog_obj} 0 R >>\nstartxref\n{startxref}\n%%EOF\n".encode("latin-1")
    )
    return bytes(out)


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
    html = article.content_html
    text = article.content_text
    if (not html or not text) and _HTTP_URL.match((article.url or "").strip()):
        extractor.fill_article(db, article, force=True)[0]
        html = article.content_html
        text = article.content_text
    body = (text or "").strip() or (article.summary or "").strip()
    if not body and html:
        body = re.sub(r"<[^>]+>", " ", html)
        body = re.sub(r"\s+", " ", body).strip()
    if not body:
        logger.info("skip pdf snapshot for article %s: no storable body", article.id)
        return None
    payload = render_article_pdf(article.title or "Untitled", body)
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
