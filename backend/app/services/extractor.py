from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import httpx
import trafilatura
from lxml import html as lxml_html
from readability import Document
from sqlalchemy.orm import Session

from app.models import Article

logger = logging.getLogger(__name__)


class ExtractFailedError(Exception):
    """Readable extract was empty or unusable; caller should keep the previous body."""

    def __init__(self, detail: str = "Extract failed, original kept.") -> None:
        super().__init__(detail)
        self.detail = detail

HEADERS = {
    "User-Agent": "Storykeep/1.0 (+https://localhost; personal archive reader)"
}

_KILL_TAGS = frozenset({"script", "style", "noscript", "svg", "nav", "footer", "aside", "iframe", "form"})
_CHROME_HINTS = (
    "cookie",
    "newsletter",
    "subscribe",
    "related",
    "share",
    "widget",
    "sidebar",
    "promo",
    "author-bio",
    "author_bio",
    "byline",
    "social",
    "comment",
    "advert",
    "ad-slot",
    "outbrain",
    "taboola",
    "signup",
    "sign-up",
)
_MAIN_QUERIES = (
    '//*[@itemprop="articleBody"]',
    "//article",
    '//*[@role="article"]',
    "//main",
)
_CSS_LINE = re.compile(
    r"^\s*(?:[.#@][\w#.\[\](),\s%-]+|\*)\s*\{",
    re.MULTILINE,
)
_CSS_PROP_LINE = re.compile(
    r"^\s*(?:box-sizing|margin|padding|display|font-|color:|background|@media|@keyframes|@import|@font-face)",
    re.I,
)
_NOISE_LINE = re.compile(
    r"^\s*(?:We use cookies|Subscribe to our|Sign up for|Related stories|Share this|Follow us on)",
    re.I,
)


def _collect_drop_targets(root: lxml_html.HtmlElement) -> list[lxml_html.HtmlElement]:
    drop: list[lxml_html.HtmlElement] = []
    seen: set[int] = set()
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        ident = id(el)
        if ident in seen:
            continue
        if el.tag in _KILL_TAGS:
            drop.append(el)
            seen.add(ident)
            continue
        if el.tag == "header" and not el.xpath("ancestor::article"):
            drop.append(el)
            seen.add(ident)
            continue
        role = (el.get("role") or "").lower()
        if role in {"navigation", "complementary", "banner"}:
            drop.append(el)
            seen.add(ident)
            continue
        hay = f"{(el.get('class') or '').lower()} {(el.get('id') or '').lower()}"
        if any(hint in hay for hint in _CHROME_HINTS):
            drop.append(el)
            seen.add(ident)
    return drop


def _prepare_html(raw: str) -> str:
    try:
        root = lxml_html.fromstring(raw)
    except Exception:
        return raw
    for el in _collect_drop_targets(root):
        parent = el.getparent()
        if parent is not None:
            el.drop_tree()
    best: lxml_html.HtmlElement | None = None
    best_len = 0
    for query in _MAIN_QUERIES:
        for node in root.xpath(query):
            text = (node.text_content() or "").strip()
            if len(text) > best_len:
                best_len = len(text)
                best = node
    if best is not None and best_len >= 120:
        return lxml_html.tostring(best, encoding="unicode")
    body = root.find(".//body")
    if body is not None:
        return lxml_html.tostring(body, encoding="unicode")
    return lxml_html.tostring(root, encoding="unicode")


def _sanitize_html(html: str) -> str:
    if not html.strip():
        return html
    try:
        root = lxml_html.fromstring(html)
    except Exception:
        return html
    for el in _collect_drop_targets(root):
        parent = el.getparent()
        if parent is not None:
            el.drop_tree()
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        el.attrib.pop("style", None)
    return lxml_html.tostring(root, encoding="unicode")


def _clean_text(text: str) -> str:
    if not text:
        return ""
    lines: list[str] = []
    seen_blocks: set[str] = set()
    blank_run = 0
    for raw in text.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            blank_run += 1
            if blank_run <= 2:
                lines.append("")
            continue
        blank_run = 0
        if _CSS_LINE.match(stripped):
            continue
        if "{" in stripped and (_CSS_PROP_LINE.match(stripped) or ".widget" in stripped):
            continue
        if _NOISE_LINE.match(stripped):
            continue
        if "box-sizing:border-box" in stripped.replace(" ", ""):
            continue
        key = re.sub(r"\s+", " ", stripped.lower())[:160]
        if len(stripped) < 320 and key in seen_blocks:
            continue
        seen_blocks.add(key)
        lines.append(stripped)
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return cleaned


def _abs_url(src: str, base: str) -> str:
    return urljoin(base, src.strip())


def _extract_image(raw_html: str, url: str, content_html: str | None = None) -> str | None:
    try:
        root = lxml_html.fromstring(raw_html)
    except Exception:
        root = None
    if root is not None:
        for query in (
            '//meta[@property="og:image"]/@content',
            '//meta[@property="og:image:url"]/@content',
            '//meta[@name="twitter:image"]/@content',
            '//meta[@name="twitter:image:src"]/@content',
        ):
            found = root.xpath(query)
            if found:
                candidate = str(found[0]).strip()
                if candidate and not candidate.startswith("data:"):
                    return _abs_url(candidate, url)[:2000]
        for link in root.xpath('//link[@rel="image_src"]/@href'):
            candidate = str(link).strip()
            if candidate:
                return _abs_url(candidate, url)[:2000]
    if content_html:
        try:
            body = lxml_html.fromstring(content_html)
            for img in body.xpath(".//img[@src]"):
                src = (img.get("src") or "").strip()
                if src and not src.startswith("data:"):
                    return _abs_url(src, url)[:2000]
        except Exception:
            pass
    return None


def _extract_from_html(html: str, url: str) -> tuple[str | None, str | None]:
    prepared = _prepare_html(html)
    downloaded = trafilatura.extract(
        prepared,
        include_comments=False,
        include_tables=True,
        output_format="html",
        url=url,
    )
    text = trafilatura.extract(prepared, include_comments=False, include_tables=True, url=url)
    if downloaded and text:
        html_out = _sanitize_html(downloaded)
        text_out = _clean_text(text)
        if text_out:
            return html_out, text_out

    try:
        doc = Document(prepared)
        cleaned = doc.summary()
        plain = trafilatura.extract(cleaned) or _strip_tags(cleaned)
        if cleaned and plain:
            html_out = _sanitize_html(cleaned)
            text_out = _clean_text(plain)
            if text_out:
                return html_out, text_out
    except Exception as exc:
        logger.info("readability failed %s: %s", url, exc)

    return None, None


def _fetch_html(url: str) -> str | None:
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=HEADERS) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text
    except Exception as exc:
        logger.info("extract fetch failed %s: %s", url, exc)
        return None


def extract_url(url: str) -> tuple[str | None, str | None, str | None]:
    raw = _fetch_html(url)
    if not raw:
        return None, None, None
    html, text = _extract_from_html(raw, url)
    image = _extract_image(raw, url, html)
    return html, text, image


def extract_html(raw_html: str, url: str = "") -> tuple[str | None, str | None]:
    """Extract readable body from raw HTML (used in tests and file ingest)."""
    return _extract_from_html(raw_html, url)


def _strip_tags(html: str) -> str:
    try:
        return lxml_html.fromstring(html).text_content().strip()
    except Exception:
        return html


def extract_page(url: str) -> tuple[str | None, str | None, str | None, str | None]:
    raw = _fetch_html(url)
    if not raw:
        return None, None, None, None
    html, text = _extract_from_html(raw, url)
    image = _extract_image(raw, url, html)
    title = None
    source = html or raw
    if source:
        try:
            tree = lxml_html.fromstring(source)
            heading = tree.find(".//h1")
            if heading is not None:
                title = (heading.text_content() or "").strip()[:500] or None
        except Exception:
            title = None
    if not title:
        title = (url.rstrip("/").rsplit("/", 1)[-1] or url)[:500]
    return html, text, title, image


def _extract_usable(html: str | None, text: str | None) -> bool:
    cleaned = _clean_text(text or "")
    if len(cleaned) < 80:
        return False
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if not lines:
        return False
    cssish = sum(1 for line in lines if _CSS_LINE.match(line) or ("{" in line and _CSS_PROP_LINE.match(line)))
    if cssish and cssish >= max(2, len(lines) // 2):
        return False
    if html:
        lowered = html.lower()
        if "<style" in lowered or "box-sizing:border-box" in lowered.replace(" ", ""):
            if len(cleaned) < 240:
                return False
    return True


def fill_article(db: Session, article: Article, force: bool = False) -> Article:
    if article.content_text and not force:
        return article
    previous_html = article.content_html
    previous_text = article.content_text
    html, text, image = extract_url(article.url)
    if not _extract_usable(html, text):
        if force and (previous_html or previous_text):
            raise ExtractFailedError("Extract failed, original kept.")
        return article
    if html:
        article.content_html = html
    if text:
        article.content_text = text
    if image:
        article.image_url = image
    article.fetched_at = datetime.now(timezone.utc)
    db.add(article)
    return article
