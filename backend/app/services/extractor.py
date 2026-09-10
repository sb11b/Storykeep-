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

    def __init__(self, detail: str = "Extract found no article text") -> None:
        super().__init__(detail)
        self.detail = detail


CHROME_NOTICE = "Page extract was chrome; kept feed text."

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
    "tip-jar",
    "tipjar",
    "tip_jar",
    "support-us",
    "support_us",
    "donate",
    "cookie-settings",
    "cookie_settings",
    "paywall",
    "membership",
    "engagement-bottom-unit",
    "engagement_bottom",
)
_MAIN_QUERIES = (
    '//*[@itemprop="articleBody"]',
    '//*[contains(concat(" ", normalize-space(@class), " "), " article__body ")]',
    '//*[contains(concat(" ", normalize-space(@class), " "), " article__main ")]',
    "//article",
    '//*[@role="article"]',
    "//main",
)
_CTA_LINE = re.compile(
    r"^\s*(?:want to leave a tip|leave a tip|support us|sign up|cookie settings|"
    r"subscribe(?:\s+to|\s+for|\s+now)?|support our|become a member|donate now|"
    r"we use cookies|accept cookies|manage cookies)",
    re.I,
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
        if _is_cta_line(stripped):
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


_CTA_PHRASES = (
    "leave a tip",
    "want to leave a tip",
    "support us",
    "sign up",
    "cookie settings",
    "support our",
    "support our journalism",
    "become a member",
    "tip jar",
    "tip-jar",
    "donate now",
    "we use cookies",
)


def _contains_cta_phrase(text: str) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in _CTA_PHRASES)


def _is_cta_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    if _CTA_LINE.match(stripped):
        return True
    if len(stripped) <= 320 and _contains_cta_phrase(stripped):
        return True
    return False


def _is_cta_only(text: str | None) -> bool:
    if not text or not text.strip():
        return True
    blocks = [block.strip() for block in re.split(r"\n{2,}", text) if block.strip()]
    if not blocks:
        return True
    substantive = [block for block in blocks if not _is_cta_line(block) and len(block) >= 40]
    return len(substantive) == 0


def _extract_paragraph_html(
    prepared: str,
    *,
    min_chars: int = 80,
    min_paragraphs: int = 1,
) -> tuple[str | None, str | None]:
    try:
        root = lxml_html.fromstring(prepared)
    except Exception:
        return None, None
    paragraphs: list[lxml_html.HtmlElement] = []
    for node in root.xpath(".//p"):
        text = (node.text_content() or "").strip()
        if not text or _is_cta_line(text):
            continue
        paragraphs.append(node)
    if len(paragraphs) < min_paragraphs:
        return None, None
    text = _clean_text("\n\n".join((p.text_content() or "").strip() for p in paragraphs))
    if len(text) < min_chars or _text_is_polluted(text) or _is_cta_only(text):
        return None, None
    html_out = _sanitize_html("".join(lxml_html.tostring(p, encoding="unicode") for p in paragraphs))
    return html_out, text


def _extract_from_article_node(prepared: str) -> tuple[str | None, str | None]:
    html_out, text = _extract_paragraph_html(prepared, min_chars=400, min_paragraphs=2)
    if html_out and text and _html_extract_candidate_valid(html_out, text):
        return html_out, text
    return None, None


def _repair_from_html(html: str) -> tuple[str | None, str | None] | None:
    prepared = _prepare_html(html)
    direct = _extract_paragraph_html(prepared, min_chars=80, min_paragraphs=1)
    if direct[0] and direct[1]:
        return direct
    return None


def _extract_from_html(html: str, url: str) -> tuple[str | None, str | None]:
    prepared = _prepare_html(html)
    direct = _extract_from_article_node(prepared)
    if direct[0] and direct[1]:
        return direct
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
        if text_out and not _is_cta_only(text_out) and _extract_usable(html_out, text_out):
            return html_out, text_out

    try:
        doc = Document(prepared)
        cleaned = doc.summary()
        plain = trafilatura.extract(cleaned) or _strip_tags(cleaned)
        if cleaned and plain:
            html_out = _sanitize_html(cleaned)
            text_out = _clean_text(plain)
            if text_out and not _is_cta_only(text_out) and _extract_usable(html_out, text_out):
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


def _text_is_polluted(text: str | None) -> bool:
    if not text or not text.strip():
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    cssish = sum(1 for line in lines if _CSS_LINE.match(line) or ("{" in line and _CSS_PROP_LINE.match(line)))
    return cssish >= max(2, len(lines) // 2)


def _html_is_polluted(html: str | None) -> bool:
    if not html or not html.strip():
        return False
    lowered = html.lower()
    if "<style" in lowered:
        return True
    compact = lowered.replace(" ", "")
    if "box-sizing:border-box" in compact or ".widget{" in compact or "{box-sizing" in compact:
        return True
    if len(_CSS_LINE.findall(html)) >= 2:
        return True
    return False


def _text_to_html(text: str) -> str:
    blocks = [block.strip() for block in text.split("\n\n") if block.strip()]
    if not blocks:
        return ""
    parts: list[str] = []
    for block in blocks:
        escaped = (
            block.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        parts.append(f"<p>{escaped.replace(chr(10), '<br />')}</p>")
    return "".join(parts)


def repair_display_body(content_html: str | None, content_text: str | None) -> tuple[str | None, str | None]:
    text = _clean_text(content_text or "")
    html = content_html
    if text and len(text) >= 40 and not _text_is_polluted(text) and not _is_cta_only(text):
        safe_html = html if html and not _html_is_polluted(html) else _text_to_html(text)
        return text, safe_html
    if html:
        repaired = _repair_from_html(html)
        if repaired:
            rep_html, rep_text = repaired
            return rep_text, rep_html
        if _html_is_polluted(html):
            stripped = _clean_text(_strip_tags(html))
            if len(stripped) >= 80 and not _text_is_polluted(stripped) and not _is_cta_only(stripped):
                return stripped, _text_to_html(stripped)
    if _is_cta_only(content_text) or _is_cta_only(text):
        return None, None
    return content_text, content_html


def _prose_paragraph_count(html: str | None, text: str | None) -> int:
    count = 0
    if html:
        try:
            root = lxml_html.fromstring(html)
            for node in root.xpath(".//p"):
                chunk = (node.text_content() or "").strip()
                if len(chunk) >= 40 and not _is_cta_line(chunk):
                    count += 1
        except Exception:
            pass
    if count:
        return count
    cleaned = _clean_text(text or "")
    if not cleaned:
        return 0
    blocks = [block.strip() for block in re.split(r"\n{2,}", cleaned) if block.strip()]
    return sum(1 for block in blocks if len(block) >= 40 and not _is_cta_line(block))


def _prose_letter_count(text: str | None) -> int:
    return sum(ch.isalpha() for ch in _clean_text(text or ""))


def _prose_char_count(text: str | None) -> int:
    return len(_clean_text(text or ""))


def _body_score(html: str | None, text: str | None) -> tuple[int, int, int]:
    return _prose_paragraph_count(html, text), _prose_letter_count(text), _prose_char_count(text)


def _feed_body_valid(html: str | None, text: str | None) -> bool:
    cleaned = _clean_text(text or "")
    if len(cleaned) < 80 or _text_is_polluted(cleaned) or _is_cta_only(cleaned):
        return False
    if html and _html_is_polluted(html):
        return False
    paragraphs, letters, _chars = _body_score(html, text)
    return paragraphs >= 1 and letters >= 80


def _html_extract_candidate_valid(html: str | None, text: str | None) -> bool:
    cleaned = _clean_text(text or "")
    if not cleaned or _text_is_polluted(cleaned) or _is_cta_only(cleaned) or _contains_cta_phrase(cleaned):
        return False
    if html and _html_is_polluted(html):
        return False
    paragraphs, _letters, chars = _body_score(html, text)
    return paragraphs >= 2 and chars >= 400


def _extract_usable(html: str | None, text: str | None) -> bool:
    return _html_extract_candidate_valid(html, text)


def _prepare_feed_body(raw_html: str | None, summary: str | None = None) -> tuple[str | None, str | None]:
    source = (raw_html or "").strip() or (summary or "").strip()
    if not source:
        return None, None
    if "<" in source:
        sanitized = _sanitize_html(source)
        repaired = _repair_from_html(sanitized)
        if repaired:
            rep_html, rep_text = repaired
            if _feed_body_valid(rep_html, rep_text):
                return rep_html, rep_text
        stripped = _clean_text(_strip_tags(sanitized))
        if _feed_body_valid(sanitized, stripped):
            return sanitized, stripped
        return None, None
    text = _clean_text(source)
    if _feed_body_valid(None, text):
        return _text_to_html(text), text
    return None, None


def resolve_feed_body(article: Article) -> tuple[str | None, str | None]:
    feed_html = getattr(article, "feed_html", None)
    feed_text = getattr(article, "feed_text", None)
    if feed_html or feed_text:
        html = feed_html
        text = feed_text or (_clean_text(_strip_tags(html)) if html else None)
        if _feed_body_valid(html, text):
            return html, text
        prepared = _prepare_feed_body(feed_html, None)
        if prepared[0] and prepared[1]:
            return prepared
    summary = getattr(article, "summary", None)
    if summary and len(summary.strip()) > 120:
        return _prepare_feed_body(summary, None)
    return None, None


def _normalize_page_candidate(html: str | None, text: str | None) -> tuple[str | None, str | None]:
    text = _clean_text(text or "") or None
    if html and _html_is_polluted(html):
        html = _text_to_html(text) if text else None
    elif html:
        html = _sanitize_html(html)
    return html, text


def pick_display_body(
    feed_html: str | None,
    feed_text: str | None,
    page_html: str | None,
    page_text: str | None,
    previous_html: str | None,
    previous_text: str | None,
    *,
    page_attempted: bool = False,
) -> tuple[str | None, str | None, str | None, str | None]:
    feed_ok = _feed_body_valid(feed_html, feed_text)
    page_ok = _html_extract_candidate_valid(page_html, page_text)
    current_ok = _html_extract_candidate_valid(previous_html, previous_text)
    feed_paragraphs, _feed_letters, feed_chars = _body_score(feed_html, feed_text) if feed_ok else (0, 0, 0)
    page_paragraphs, _page_letters, page_chars = _body_score(page_html, page_text) if page_ok else (0, 0, 0)
    _current_paragraphs, _current_letters, current_chars = _body_score(previous_html, previous_text)
    page_attempted = page_attempted or bool(page_html or page_text)
    chrome_notice = CHROME_NOTICE if page_attempted and not page_ok else None

    if page_ok and page_chars >= feed_chars and (not current_ok or page_chars >= current_chars):
        return page_html, page_text, None, "page"
    if feed_ok and (not current_ok or feed_chars > current_chars):
        return feed_html, feed_text, chrome_notice, "feed"
    if current_ok:
        return previous_html, previous_text, chrome_notice, "previous"
    if feed_ok:
        return feed_html, feed_text, chrome_notice, "feed"
    if page_ok:
        return page_html, page_text, None, "page"
    return None, None, chrome_notice, None


def restore_feed_body(db: Session, article: Article) -> Article:
    feed_html, feed_text = resolve_feed_body(article)
    if not feed_html and not feed_text:
        from app.services import rss

        raw = rss.refetch_entry_html(db, article)
        if raw:
            prepared_html, prepared_text = _prepare_feed_body(raw)
            if prepared_html and prepared_text:
                article.feed_html = raw
                article.feed_text = prepared_text
                feed_html, feed_text = prepared_html, prepared_text
    if not feed_html and not feed_text:
        raise ExtractFailedError("No feed text available for this article")
    if article.feed_html is None and feed_html:
        article.feed_html = feed_html
    if article.feed_text is None and feed_text:
        article.feed_text = feed_text
    article.content_html = feed_html or _text_to_html(feed_text or "")
    article.content_text = feed_text or _clean_text(_strip_tags(feed_html or ""))
    db.add(article)
    return article


def _ensure_feed_body(db: Session, article: Article, refetch: bool = False) -> tuple[str | None, str | None]:
    feed_html, feed_text = resolve_feed_body(article)
    if feed_html and feed_text:
        return feed_html, feed_text
    if not refetch:
        return feed_html, feed_text
    from app.services import rss

    raw = rss.refetch_entry_html(db, article)
    if not raw:
        return feed_html, feed_text
    article.feed_html = raw
    prepared_html, prepared_text = _prepare_feed_body(raw)
    if prepared_text:
        article.feed_text = prepared_text
        return prepared_html or _text_to_html(prepared_text), prepared_text
    return feed_html, feed_text


def fill_article(db: Session, article: Article, force: bool = False) -> tuple[Article, str | None]:
    feed_html, feed_text = _ensure_feed_body(db, article, refetch=force)
    if feed_html and getattr(article, "feed_html", None) is None:
        article.feed_html = feed_html
    if feed_text and getattr(article, "feed_text", None) is None:
        article.feed_text = feed_text

    previous_html = article.content_html
    previous_text = article.content_text
    previous_image = article.image_url

    if (
        not force
        and article.content_text
        and _html_extract_candidate_valid(article.content_html, article.content_text)
    ):
        return article, None

    page_html: str | None = None
    page_text: str | None = None
    image: str | None = None
    raw = _fetch_html(article.url)
    page_attempted = bool(raw)
    if raw:
        page_html, page_text = _extract_from_html(raw, article.url)
        page_html, page_text = _normalize_page_candidate(page_html, page_text)
        if not _html_extract_candidate_valid(page_html, page_text):
            page_html, page_text = None, None
        image = _extract_image(raw, article.url, page_html)

    chosen_html, chosen_text, notice, source = pick_display_body(
        feed_html,
        feed_text,
        page_html,
        page_text,
        previous_html,
        previous_text,
        page_attempted=page_attempted,
    )

    if not chosen_html and not chosen_text:
        if force and not (previous_html or previous_text or feed_html or feed_text):
            raise ExtractFailedError()
        return article, notice or (CHROME_NOTICE if raw else None)

    next_html = chosen_html or _text_to_html(chosen_text or "")
    next_text = chosen_text or _clean_text(_strip_tags(chosen_html or ""))
    if source == "page" and not _html_extract_candidate_valid(next_html, next_text):
        return article, CHROME_NOTICE
    if (
        (previous_html or "").strip() == (next_html or "").strip()
        and (previous_text or "").strip() == (next_text or "").strip()
    ):
        return article, notice

    article.content_html = next_html
    article.content_text = next_text
    if image:
        article.image_url = image
    elif force and previous_image:
        article.image_url = previous_image
    if source == "page":
        article.fetched_at = datetime.now(timezone.utc)
    db.add(article)
    return article, notice
