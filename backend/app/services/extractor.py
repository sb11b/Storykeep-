from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import httpx
import trafilatura
from lxml import html as lxml_html
from readability import Document
from sqlalchemy.orm import Session

from app.models import Article

logger = logging.getLogger(__name__)

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


def extract_url(url: str) -> tuple[str | None, str | None]:
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=HEADERS) as client:
            response = client.get(url)
            response.raise_for_status()
            html = response.text
    except Exception as exc:
        logger.info("extract fetch failed %s: %s", url, exc)
        return None, None
    return _extract_from_html(html, url)


def extract_html(raw_html: str, url: str = "") -> tuple[str | None, str | None]:
    """Extract readable body from raw HTML (used in tests and file ingest)."""
    return _extract_from_html(raw_html, url)


def _strip_tags(html: str) -> str:
    try:
        return lxml_html.fromstring(html).text_content().strip()
    except Exception:
        return html


def extract_page(url: str) -> tuple[str | None, str | None, str | None]:
    html, text = extract_url(url)
    title = None
    source = html or ""
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
    return html, text, title


def fill_article(db: Session, article: Article, force: bool = False) -> Article:
    if article.content_text and not force:
        return article
    html, text = extract_url(article.url)
    if html:
        article.content_html = html
    if text:
        article.content_text = text
    if html or text:
        article.fetched_at = datetime.now(timezone.utc)
    db.add(article)
    return article
