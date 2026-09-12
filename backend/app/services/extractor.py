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
FULL_TEXT_UNAVAILABLE = "Full text unavailable"
CBR_NO_COLUMN_NOTICE = "CBR page returned no article column; kept dek."
DEK_MIN_PARAGRAPHS = 3
DEK_MIN_CHARS = 500
CBR_REFERER = "https://www.cbr.com/"
_CBR_HOSTS = ("cbr.com", "www.cbr.com")
_CBR_ARTICLE_XPATHS = (
    '//*[contains(concat(" ", normalize-space(@class), " "), " article-body ")]',
    '//*[contains(@class, "article-body")]',
    '//article[contains(@class, "w-article")]//div[contains(@class, "article-body")]',
    '//article[contains(@class, "w-article")]',
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; Storykeep/1.0; +https://storykeep.app) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_KILL_TAGS = frozenset({"script", "style", "noscript", "svg", "nav", "footer", "aside", "iframe", "form"})
_CHROME_HINTS = (
    "cookie",
    "newsletter",
    "subscribe",
    "related",
    "share",
    "related-widget",
    "sidebar-widget",
    "share-widget",
    "outbrain-widget",
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
    "newsletter-signup",
)
_PROTECTED_ARTICLE_MARKERS = (
    "article-body",
    "article__body",
    "article-content",
    "article-main",
    "article__main",
    "w-article",
    "entry-content",
    "post-content",
)
_MAIN_QUERIES = (
    '//*[@itemprop="articleBody"]',
    '//*[contains(concat(" ", normalize-space(@class), " "), " article-body ")]',
    '//*[contains(concat(" ", normalize-space(@class), " "), " article__body ")]',
    '//*[contains(concat(" ", normalize-space(@class), " "), " article__main ")]',
    "//article",
    '//*[@role="article"]',
    "//main",
)
_BLOCK_TAGS = ("h2", "h3", "h4", "p", "ul", "ol", "blockquote")
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


def _is_protected_article_node(el: lxml_html.HtmlElement) -> bool:
    if el.tag == "article":
        return True
    hay = f"{(el.get('class') or '').lower()} {(el.get('id') or '').lower()}"
    return any(marker in hay for marker in _PROTECTED_ARTICLE_MARKERS)


def _collect_drop_targets(root: lxml_html.HtmlElement) -> list[lxml_html.HtmlElement]:
    drop: list[lxml_html.HtmlElement] = []
    seen: set[int] = set()
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        ident = id(el)
        if ident in seen:
            continue
        if _is_protected_article_node(el):
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


def _extract_meta_image(raw_html: str, url: str) -> str | None:
    try:
        root = lxml_html.fromstring(raw_html)
    except Exception:
        return None
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
    return None


def _first_content_image(content_html: str, url: str) -> str | None:
    if not content_html:
        return None
    try:
        body = lxml_html.fromstring(content_html)
        for img in body.xpath(".//img[@src]"):
            src = (img.get("src") or "").strip()
            if src and not src.startswith("data:"):
                return _abs_url(src, url)[:2000]
    except Exception:
        pass
    return None


def _extract_image(raw_html: str, url: str, content_html: str | None = None) -> str | None:
    meta = _extract_meta_image(raw_html, url)
    if meta:
        return meta
    if content_html:
        return _first_content_image(content_html, url)
    return None


def ensure_article_image(db: Session, article: Article, raw_html: str | None = None) -> bool:
    """Backfill article.image_url from page meta tags when still empty."""
    if article.image_url:
        return False
    if raw_html:
        image = _extract_meta_image(raw_html, article.url)
    else:
        raw = _fetch_html(article.url)
        image = _extract_meta_image(raw, article.url) if raw else None
    if not image:
        return False
    article.image_url = image
    db.add(article)
    return True


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


def _collect_article_blocks(root: lxml_html.HtmlElement) -> list[lxml_html.HtmlElement]:
    candidates: list[lxml_html.HtmlElement] = []
    for tag in _BLOCK_TAGS:
        candidates.extend(root.xpath(f".//{tag}"))
    if not candidates:
        return []
    candidate_ids = {id(node) for node in candidates}
    blocks: list[lxml_html.HtmlElement] = []
    for node in candidates:
        if node.tag in {"li"}:
            continue
        if any(id(ancestor) in candidate_ids for ancestor in node.iterancestors()):
            continue
        text = (node.text_content() or "").strip()
        if not text or _is_cta_line(text):
            continue
        blocks.append(node)
    return blocks


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
    blocks = _collect_article_blocks(root)
    prose_blocks = [block for block in blocks if block.tag == "p" or block.tag.startswith("h")]
    if len(prose_blocks) < min_paragraphs and len(blocks) < min_paragraphs:
        return None, None
    text = _clean_text("\n\n".join((block.text_content() or "").strip() for block in blocks))
    if len(text) < min_chars or _text_is_polluted(text) or _is_cta_only(text):
        return None, None
    html_out = _sanitize_html("".join(lxml_html.tostring(block, encoding="unicode") for block in blocks))
    return html_out, text


def _extract_from_article_node(prepared: str) -> tuple[str | None, str | None]:
    html_out, text = _extract_paragraph_html(prepared, min_chars=400, min_paragraphs=2)
    if html_out and text and _html_extract_candidate_valid(html_out, text):
        return html_out, text
    return None, None


def _is_cbr_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        from urllib.parse import urlparse

        host = (urlparse(url).netloc or "").lower()
    except Exception:
        host = url.lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in _CBR_HOSTS)


def _cbr_notice(char_count: int, updated: bool) -> str:
    if updated and char_count > 0:
        return f"Updated from cbr.com ({char_count} chars)"
    return CBR_NO_COLUMN_NOTICE


def _find_cbr_article_root(root: lxml_html.HtmlElement) -> lxml_html.HtmlElement | None:
    best: lxml_html.HtmlElement | None = None
    best_score = 0
    for query in _CBR_ARTICLE_XPATHS:
        for node in root.xpath(query):
            if not isinstance(node.tag, str):
                continue
            hay = f"{(node.get('class') or '').lower()} {(node.get('id') or '').lower()}"
            text_len = len((node.text_content() or "").strip())
            score = text_len + (1_000_000 if "article-body" in hay else 0)
            if score > best_score:
                best_score = score
                best = node
    return best


def _extract_cbr_article_body(raw: str, url: str) -> tuple[str | None, str | None, int]:
    try:
        root = lxml_html.fromstring(raw)
    except Exception as exc:
        logger.info("cbr parse failed %s: %s", url, exc)
        return None, None, 0

    article_root = _find_cbr_article_root(root)
    if article_root is None:
        return None, None, 0

    blocks = _collect_article_blocks(article_root)
    if not blocks:
        blocks = []
        for node in article_root.xpath(".//p"):
            text = (node.text_content() or "").strip()
            if len(text) >= 40 and not _is_cta_line(text):
                blocks.append(node)
    if not blocks:
        return None, None, 0

    text = _clean_text("\n\n".join((block.text_content() or "").strip() for block in blocks))
    char_count = len(text)
    if char_count < 80 or _text_is_polluted(text) or _is_cta_only(text):
        return None, None, char_count

    html_out = _sanitize_html("".join(lxml_html.tostring(block, encoding="unicode") for block in blocks))
    return html_out, text, char_count


def _extract_with_readability_fallback(prepared: str, url: str) -> tuple[str | None, str | None]:
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
        if text_out and not _is_cta_only(text_out) and len(text_out) >= DEK_MIN_CHARS:
            return html_out, text_out

    try:
        doc = Document(prepared)
        cleaned = doc.summary()
        plain = trafilatura.extract(cleaned) or _strip_tags(cleaned)
        if cleaned and plain:
            html_out = _sanitize_html(cleaned)
            text_out = _clean_text(plain)
            if text_out and not _is_cta_only(text_out) and len(text_out) >= DEK_MIN_CHARS:
                return html_out, text_out
    except Exception as exc:
        logger.info("readability failed %s: %s", url, exc)
    return None, None


def _extract_cbr_page(raw: str, url: str, *, status: int | None = None) -> tuple[str | None, str | None, int, str]:
    html_out, text_out, char_count = _extract_cbr_article_body(raw, url)
    logger.info(
        "cbr extract url=%s status=%s extracted_char_count=%s",
        url,
        status if status is not None else "unknown",
        char_count,
    )
    if char_count >= DEK_MIN_CHARS and html_out and text_out:
        return html_out, text_out, char_count, "article-body"

    fallback_html, fallback_text = _extract_with_readability_fallback(raw, url)
    fallback_count = len(_clean_text(fallback_text or ""))
    if fallback_count >= DEK_MIN_CHARS and fallback_html and fallback_text:
        logger.info(
            "cbr extract fallback url=%s status=%s extracted_char_count=%s method=readability",
            url,
            status if status is not None else "unknown",
            fallback_count,
        )
        return fallback_html, fallback_text, fallback_count, "readability"
    return html_out, text_out, char_count, "none"


def _repair_from_html(html: str) -> tuple[str | None, str | None] | None:
    prepared = _prepare_html(html)
    direct = _extract_paragraph_html(prepared, min_chars=80, min_paragraphs=1)
    if direct[0] and direct[1]:
        return direct
    return None


def _extract_from_html(html: str, url: str) -> tuple[str | None, str | None]:
    if _is_cbr_url(url):
        page_html, page_text, _char_count, _method = _extract_cbr_page(html, url)
        if page_html and page_text and len(page_text) >= DEK_MIN_CHARS:
            return page_html, page_text

    prepared = _prepare_html(html)
    direct = _extract_from_article_node(prepared)
    if direct[0] and direct[1]:
        return direct
    fallback_html, fallback_text = _extract_with_readability_fallback(prepared, url)
    if fallback_html and fallback_text and _extract_usable(fallback_html, fallback_text):
        return fallback_html, fallback_text
    return None, None


def _fetch_error_message(url: str, status: int | None, exc: Exception | None = None) -> str | None:
    if status is not None:
        if _is_cbr_url(url):
            return f"CBR returned {status}"
        return f"Page returned {status}"
    if exc is not None:
        text = str(exc).strip()
        return text or None
    return None


def _fetch_html_with_status(url: str) -> tuple[str | None, int | None, str | None]:
    last_error: Exception | None = None
    last_status: int | None = None
    last_message: str | None = None
    request_headers = dict(HEADERS)
    if _is_cbr_url(url):
        request_headers["Referer"] = CBR_REFERER
    else:
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                request_headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"
        except Exception:
            pass
    for attempt in range(3):
        try:
            with httpx.Client(timeout=30.0, follow_redirects=True, headers=request_headers) as client:
                response = client.get(url)
                status = response.status_code
                response.raise_for_status()
                text = response.text or ""
                logger.info("extract fetch url=%s status=%s bytes=%s attempt=%s", url, status, len(text), attempt + 1)
                if len(text) >= 500:
                    return text, status, None
                last_error = ValueError(f"short response ({len(text)} bytes)")
                last_status = status
                last_message = _fetch_error_message(url, status, last_error)
        except httpx.HTTPStatusError as exc:
            last_error = exc
            last_status = exc.response.status_code
            last_message = _fetch_error_message(url, last_status, exc)
            logger.info("extract fetch attempt %s failed %s: %s", attempt + 1, url, last_message)
        except Exception as exc:
            last_error = exc
            last_message = _fetch_error_message(url, last_status, exc)
            logger.info("extract fetch attempt %s failed %s: %s", attempt + 1, url, exc)
    if last_error:
        logger.warning("extract fetch failed %s: %s", url, last_message or last_error)
    return None, last_status, last_message


def _fetch_html(url: str) -> str | None:
    raw, _status, _message = _fetch_html_with_status(url)
    return raw


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


def _is_dek_only(html: str | None, text: str | None) -> bool:
    cleaned = _clean_text(text or "")
    if not cleaned or len(cleaned) < 80 or _text_is_polluted(cleaned) or _is_cta_only(cleaned):
        return True
    paragraphs, _letters, chars = _body_score(html, text)
    return paragraphs < DEK_MIN_PARAGRAPHS or chars < DEK_MIN_CHARS


def _feed_body_valid(html: str | None, text: str | None) -> bool:
    if _is_dek_only(html, text):
        return False
    cleaned = _clean_text(text or "")
    if _text_is_polluted(cleaned) or _is_cta_only(cleaned):
        return False
    if html and _html_is_polluted(html):
        return False
    paragraphs, letters, _chars = _body_score(html, text)
    return paragraphs >= 1 and letters >= 80


def _feed_storage_body(raw_html: str | None, summary: str | None = None) -> tuple[str | None, str | None]:
    source = (raw_html or "").strip() or (summary or "").strip()
    if not source:
        return None, None
    if "<" in source:
        sanitized = _sanitize_html(source)
        text = _clean_text(_strip_tags(sanitized))
        if text:
            return sanitized, text
        return None, None
    text = _clean_text(source)
    return (_text_to_html(text), text) if text else (None, None)


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
        storage = _feed_storage_body(feed_html, None)
        if storage[0] and storage[1]:
            return storage
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
    page_fetched: bool = False,
) -> tuple[str | None, str | None, str | None, str | None]:
    feed_full = _feed_body_valid(feed_html, feed_text)
    page_ok = _html_extract_candidate_valid(page_html, page_text)
    current_ok = _html_extract_candidate_valid(previous_html, previous_text)
    feed_is_dek = _is_dek_only(feed_html, feed_text)
    current_is_dek = _is_dek_only(previous_html, previous_text)
    feed_paragraphs, _feed_letters, feed_chars = _body_score(feed_html, feed_text) if feed_html or feed_text else (0, 0, 0)
    page_paragraphs, _page_letters, page_chars = _body_score(page_html, page_text) if page_ok else (0, 0, 0)
    _current_paragraphs, _current_letters, current_chars = _body_score(previous_html, previous_text)
    page_attempted = page_attempted or bool(page_html or page_text)
    unavailable_notice = (
        FULL_TEXT_UNAVAILABLE if page_attempted and not page_fetched and not current_ok else None
    )
    chrome_notice = CHROME_NOTICE if page_attempted and page_fetched and not page_ok else None

    if page_ok and (feed_is_dek or not feed_full or page_chars >= feed_chars or not current_ok):
        return page_html, page_text, None, "page"
    if current_ok and not page_ok:
        return previous_html, previous_text, unavailable_notice, "previous"
    if feed_full and (not current_ok or feed_chars > current_chars):
        return feed_html, feed_text, chrome_notice, "feed"
    if current_ok:
        return previous_html, previous_text, unavailable_notice, "previous"
    if feed_full:
        return feed_html, feed_text, chrome_notice, "feed"
    if page_ok:
        return page_html, page_text, None, "page"
    if (feed_html or feed_text) and (feed_chars >= current_chars or not current_ok):
        return feed_html, feed_text, unavailable_notice or chrome_notice, "feed"
    if previous_html or previous_text:
        return previous_html, previous_text, unavailable_notice, "previous"
    return None, None, unavailable_notice, None


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
    prepared_html, prepared_text = _feed_storage_body(raw)
    if prepared_text:
        article.feed_text = prepared_text
        return prepared_html or _text_to_html(prepared_text), prepared_text
    return feed_html, feed_text


def article_needs_page_extract(article: Article) -> bool:
    return _is_dek_only(article.content_html, article.content_text) or not _html_extract_candidate_valid(
        article.content_html, article.content_text
    )


def has_full_text(html: str | None, text: str | None) -> bool:
    return _html_extract_candidate_valid(html, text) and not _is_dek_only(html, text)


def _is_long_stored_body(html: str | None, text: str | None) -> bool:
    return has_full_text(html, text)


def _body_longer_than(page_html: str | None, page_text: str | None, previous_html: str | None, previous_text: str | None) -> bool:
    _page_paras, _page_letters, page_chars = _body_score(page_html, page_text)
    _prev_paras, _prev_letters, prev_chars = _body_score(previous_html, previous_text)
    return page_chars > prev_chars


def _apply_extracted_image(
    db: Session,
    article: Article,
    image: str | None,
    raw_html: str | None,
    *,
    previous_image: str | None,
    force: bool,
) -> None:
    if image:
        article.image_url = image
        db.add(article)
    elif not article.image_url:
        ensure_article_image(db, article, raw_html=raw_html)
    elif force and previous_image and not image:
        article.image_url = previous_image
        db.add(article)


def fill_article(db: Session, article: Article, force: bool = False) -> tuple[Article, str | None]:
    feed_html, feed_text = _ensure_feed_body(db, article, refetch=force)
    if feed_html and getattr(article, "feed_html", None) is None:
        article.feed_html = feed_html
    if feed_text and getattr(article, "feed_text", None) is None:
        article.feed_text = feed_text

    previous_html = article.content_html
    previous_text = article.content_text
    previous_image = article.image_url
    needs_page = force or article_needs_page_extract(article) or _is_dek_only(feed_html, feed_text)

    if _is_long_stored_body(previous_html, previous_text):
        if not article.image_url:
            ensure_article_image(db, article)
        return article, None

    if not needs_page and has_full_text(article.content_html, article.content_text):
        if not article.image_url:
            ensure_article_image(db, article)
        return article, None

    page_html: str | None = None
    page_text: str | None = None
    image: str | None = None
    raw: str | None = None
    fetch_status: int | None = None
    fetch_error: str | None = None
    page_attempted = needs_page
    if needs_page:
        raw, fetch_status, fetch_error = _fetch_html_with_status(article.url)
    if needs_page and _is_cbr_url(article.url) and not raw:
        if force and fetch_error:
            raise ExtractFailedError(fetch_error)
        return article, fetch_error or CBR_NO_COLUMN_NOTICE
    if raw and _is_cbr_url(article.url):
        page_html, page_text, cbr_char_count, _method = _extract_cbr_page(raw, article.url, status=fetch_status)
        page_html, page_text = _normalize_page_candidate(page_html, page_text)
        image = _extract_image(raw, article.url, page_html)
        if (
            page_html
            and page_text
            and cbr_char_count >= DEK_MIN_CHARS
            and _body_longer_than(page_html, page_text, previous_html, previous_text)
        ):
            article.content_html = page_html
            article.content_text = page_text
            _apply_extracted_image(
                db, article, image, raw, previous_image=previous_image, force=force
            )
            article.fetched_at = datetime.now(timezone.utc)
            db.add(article)
            return article, _cbr_notice(cbr_char_count, True)
        _apply_extracted_image(db, article, image, raw, previous_image=previous_image, force=force)
        return article, CBR_NO_COLUMN_NOTICE

    if raw:
        page_html, page_text = _extract_from_html(raw, article.url)
        page_html, page_text = _normalize_page_candidate(page_html, page_text)
        if page_html and page_text and not _html_extract_candidate_valid(page_html, page_text):
            if not _body_longer_than(page_html, page_text, previous_html, previous_text):
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
        page_fetched=bool(raw),
    )

    if not chosen_html and not chosen_text:
        if force and not (previous_html or previous_text or feed_html or feed_text):
            raise ExtractFailedError()
        _apply_extracted_image(db, article, image, raw, previous_image=previous_image, force=force)
        return article, notice or (FULL_TEXT_UNAVAILABLE if page_attempted else None)

    next_html = chosen_html or _text_to_html(chosen_text or "")
    next_text = chosen_text or _clean_text(_strip_tags(chosen_html or ""))
    if source == "page" and not _html_extract_candidate_valid(next_html, next_text):
        _apply_extracted_image(db, article, image, raw, previous_image=previous_image, force=force)
        return article, CHROME_NOTICE
    if (
        (previous_html or "").strip() == (next_html or "").strip()
        and (previous_text or "").strip() == (next_text or "").strip()
    ):
        _apply_extracted_image(db, article, image, raw, previous_image=previous_image, force=force)
        return article, notice

    if not _body_longer_than(next_html, next_text, previous_html, previous_text):
        _apply_extracted_image(db, article, image, raw, previous_image=previous_image, force=force)
        return article, notice

    article.content_html = next_html
    article.content_text = next_text
    _apply_extracted_image(db, article, image, raw, previous_image=previous_image, force=force)
    if source == "page":
        article.fetched_at = datetime.now(timezone.utc)
    db.add(article)
    return article, notice
