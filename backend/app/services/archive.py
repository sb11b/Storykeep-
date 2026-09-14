from __future__ import annotations

import hashlib
import html as html_lib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from urllib.parse import urljoin

from sqlalchemy.orm import Session
from weasyprint import HTML as WeasyHTML

from lxml import html as lxml_html

from app.config import settings
from app.models import Archive, Article
from app.services import extractor
from app.services.backup import object_store_ready, upload_object_file

logger = logging.getLogger(__name__)
_HTTP_URL = re.compile(r"^https?://", re.I)
_HTML_MARK = re.compile(r"</?(?:p|h[1-6]|ul|ol|li|img|article|blockquote|figure|br|div)\b", re.I)
_TRACKER_URL = re.compile(
    r"(?:pixel|1x1|tracking|doubleclick|googletagmanager|google-analytics|"
    r"facebook\.com/tr|scorecardresearch|quantserve|/beacon|analytics\.)",
    re.I,
)
_WEBFONT_URL = re.compile(
    r"(?:fonts\.googleapis|fonts\.gstatic|use\.typekit|typekit\.net|fonts\.adobe)",
    re.I,
)
_SNAPSHOT_CHROME = (
    "onetrust",
    "cookiebot",
    "cookie-banner",
    "cookie_banner",
    "cookie-notice",
    "cookie-consent",
    "consent-banner",
    "gdpr",
    "cc-banner",
    "sp_message",
    "privacy-banner",
    "share-bar",
    "sharebar",
    "share-buttons",
    "social-share",
    "sharing-tools",
    "related-rail",
    "related_rail",
    "related-stories",
    "recirc",
    "recommended-stories",
    "site-nav",
    "site-header",
    "masthead",
    "global-header",
    "global-nav",
    "site-footer",
    "page-footer",
    "footer-chrome",
)
_LAZY_SRC = ("data-src", "data-original", "data-lazy-src", "data-url")
_LAZY_SRCSET = ("data-srcset", "data-lazy-srcset")
PDF_SNAPSHOT_TYPES = {"pdf"}
PDF_RENDERER = "weasyprint"


def _https_abs(url: str, base_url: str) -> str:
    value = (url or "").strip()
    if not value or value.startswith(("data:", "mailto:", "javascript:", "#")):
        return value
    if value.startswith("//"):
        value = "https:" + value
    elif not _HTTP_URL.match(value):
        value = urljoin(base_url or "", value)
    if value.startswith("http://"):
        value = "https://" + value[len("http://") :]
    return value


def _is_tracker_or_pixel(el: lxml_html.HtmlElement) -> bool:
    width = (el.get("width") or "").strip().rstrip("px")
    height = (el.get("height") or "").strip().rstrip("px")
    if width == "1" and height == "1":
        return True
    src = el.get("src") or ""
    srcset = el.get("srcset") or ""
    hay = f"{src} {srcset} {(el.get('class') or '')} {(el.get('id') or '')}"
    return bool(_TRACKER_URL.search(hay))


def _drop_snapshot_chrome(root: lxml_html.HtmlElement) -> None:
    drop: list[lxml_html.HtmlElement] = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if el.tag in {"link", "style", "meta", "font"}:
            drop.append(el)
            continue
        href = el.get("href") or ""
        if el.tag == "a" and _WEBFONT_URL.search(href):
            continue
        hay = f"{(el.get('class') or '').lower()} {(el.get('id') or '').lower()} {href.lower()}"
        if any(hint in hay for hint in _SNAPSHOT_CHROME):
            if extractor._is_protected_article_node(el):
                continue
            drop.append(el)
            continue
        if el.tag in {"img", "source"} and _is_tracker_or_pixel(el):
            drop.append(el)
    for el in drop:
        parent = el.getparent()
        if parent is not None:
            el.drop_tree()


def _promote_lazy_media(root: lxml_html.HtmlElement, base_url: str) -> None:
    for el in list(root.iter()):
        if not isinstance(el.tag, str):
            continue
        if el.tag in {"img", "source", "video"}:
            src = (el.get("src") or "").strip()
            if not src:
                for attr in _LAZY_SRC:
                    candidate = (el.get(attr) or "").strip()
                    if candidate:
                        el.set("src", candidate)
                        break
            srcset = (el.get("srcset") or "").strip()
            if not srcset:
                for attr in _LAZY_SRCSET:
                    candidate = (el.get(attr) or "").strip()
                    if candidate:
                        el.set("srcset", candidate)
                        break
            for attr in (*_LAZY_SRC, *_LAZY_SRCSET):
                if attr in el.attrib:
                    el.attrib.pop(attr, None)
        for attr in ("src", "href"):
            value = el.get(attr)
            if not value or value.startswith(("data:", "mailto:", "javascript:", "#")):
                continue
            if _WEBFONT_URL.search(value):
                if attr == "href" and el.tag == "link":
                    parent = el.getparent()
                    if parent is not None:
                        el.drop_tree()
                    break
                continue
            el.set(attr, _https_abs(value, base_url))
        srcset = el.get("srcset")
        if not srcset:
            continue
        parts: list[str] = []
        for item in srcset.split(","):
            item = item.strip()
            if not item:
                continue
            bits = item.split()
            url = _https_abs(bits[0], base_url)
            if url.startswith("data:") or _TRACKER_URL.search(url):
                continue
            rest = " ".join(bits[1:])
            parts.append(f"{url} {rest}".strip())
        if parts:
            el.set("srcset", ", ".join(parts))
        elif "srcset" in el.attrib:
            el.attrib.pop("srcset", None)


def _prefer_article_fragment(root: lxml_html.HtmlElement) -> lxml_html.HtmlElement:
    best: lxml_html.HtmlElement | None = None
    best_len = 0
    for query in extractor._MAIN_QUERIES:
        for node in root.xpath(query):
            text = (node.text_content() or "").strip()
            if len(text) > best_len:
                best_len = len(text)
                best = node
    if best is not None and best_len >= 80:
        return best
    return root


def _polish_html_snapshot(html: str, base_url: str) -> str:
    if not html.strip():
        return html
    try:
        root = lxml_html.fromstring(html)
    except Exception:
        return html
    _drop_snapshot_chrome(root)
    root = _prefer_article_fragment(root)
    _promote_lazy_media(root, base_url)
    _drop_snapshot_chrome(root)
    return lxml_html.tostring(root, encoding="unicode")


def _html_has_readable_structure(html: str) -> bool:
    if not html.strip():
        return False
    if _HTML_MARK.search(html):
        return True
    return len(extractor._strip_tags(html).strip()) >= 40


def readable_article_html(html: str | None, text: str | None, base_url: str | None = None) -> str:
    """Main-content HTML for an HTML snapshot/restore. Does not flatten structure."""
    raw = (html or "").strip()
    base = (base_url or "").strip()
    if raw and _HTML_MARK.search(raw):
        prepared = extractor._prepare_html(raw)
        cleaned = _polish_html_snapshot(extractor._sanitize_html(prepared), base)
        if _html_has_readable_structure(cleaned):
            return cleaned
        fallback = _polish_html_snapshot(extractor._sanitize_html(raw), base)
        if _html_has_readable_structure(fallback):
            return fallback
    prose = (text or "").strip()
    if prose:
        wrapped = extractor._text_to_html(prose) or extractor._sanitize_html(f"<p>{html_lib.escape(prose)}</p>")
        return _polish_html_snapshot(extractor._sanitize_html(wrapped), base)
    if raw:
        return _polish_html_snapshot(extractor._sanitize_html(raw), base)
    return ""

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
    previous_html = article.content_html
    previous_text = article.content_text
    payload = readable_article_html(previous_html, previous_text, article.url)
    if not payload.strip():
        logger.info("skip snapshot for article %s: no storable body", article.id)
        return None
    article.content_html = previous_html
    article.content_text = previous_text
    digest = hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()
    existing = next((row for row in (article.archives or []) if row.checksum == digest), None)
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
    try:
        html = readable_article_html(raw, None, getattr(article, "url", None))
    except Exception as exc:
        raise ValueError("That HTML snapshot could not be restored.") from exc
    if not html.strip():
        raise ValueError("That HTML snapshot has no readable article.")
    text = extractor._clean_text(extractor._strip_tags(html)) if html else ""
    article.content_html = html
    article.content_text = text or None
    article.offline_view = "html"
    article.offline_archive_id = row.id
    db.add(article)
