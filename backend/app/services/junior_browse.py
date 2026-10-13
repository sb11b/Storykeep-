"""Server-side page fetch for Junior's browse tool.

Junior's `fetch_web_page` function tool asks for ONE arbitrary public URL —
the voice session already carries xAI's built-in `web_search` (which returns
snippets and never the body), so the missing capability is a full-page
read. This service owns that round trip and nothing else: validate, fetch,
extract readable text. It deliberately does NOT reuse
`services.extractor`, which is the feed-ingest pipeline — it writes Article
rows, applies site-specific hacks (CBR), and gates on feed-shaped usability
rules (`_extract_usable` needs >=2 prose paragraphs), so a valid short page
would be rejected. Here we extract with trafilatura directly and return
whatever prose we find.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Read cap for a page Junior reads aloud. A full article is 10k–40k chars;
# the offset/continuation contract lets him ask for the next chunk.
PAGE_TEXT_CHARS = 40_000
MAX_URL_CHARS = 2_000
# Refuse to buffer a runaway response: cap the raw download, not just the
# extracted text, so a multi-megabyte page can't sit in memory.
MAX_RESPONSE_BYTES = 4_000_000
FETCH_TIMEOUT_SEC = 20.0
FETCH_CONNECT_SEC = 8.0

ALLOWED_SCHEMES = frozenset({"http", "https"})
# Private/link-local/loopback ranges are the SSRF targets; a voice tool that
# fetches Steve's cloud metadata endpoint or his LAN is not a feature.
_BLOCKED_HOST_RE = re.compile(
    r"^(?:"
    r"localhost|127\.[0-9.]+|0\.0\.0\.0|\[?::1\]?|\[?::ffff:127\.[0-9.]+\]?|"
    r"10\.[0-9.]+|192\.168\.[0-9.]+|172\.(?:1[6-9]|2[0-9]|3[01])\.[0-9.]+|"
    r"169\.254\.[0-9.]+"
    r")$",
    re.I,
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; Storykeep/1.0; +https://storykeep.app) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class PageFetchError(Exception):
    """The page could not be fetched or held no readable text."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass
class PageText:
    url: str
    title: str
    text: str


def is_allowed_url(url: str) -> bool:
    """True only for a public http(s) URL — no other scheme, no private host.

    Deliberately conservative: it is the gate in front of an outbound request
    driven by model output, so anything it cannot positively classify is
    refused.
    """
    if not url or len(url) > MAX_URL_CHARS:
        return False
    if any(ch.isspace() for ch in url):
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if (parsed.scheme or "").lower() not in ALLOWED_SCHEMES:
        return False
    if not parsed.hostname:
        return False
    if _BLOCKED_HOST_RE.match(parsed.hostname.strip("[]")):
        return False
    return True


def _extract_title(html: str, url: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    if match:
        title = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", match.group(1))).strip()
        if title:
            return title[:500]
    return (url.rstrip("/").rsplit("/", 1)[-1] or url)[:500]


def extract_readable_text(html: str, url: str = "") -> tuple[str, str]:
    """Readable body text + title from raw HTML. Never raises.

    Uses trafilatura (the same extractor the feed pipeline uses) with a plain
    lxml text fallback, so a page without an obvious article node still
    yields something Junior can read.
    """
    title = _extract_title(html, url)
    text = ""
    if html.strip():
        try:
            import trafilatura

            extracted = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                url=url or None,
                favor_recall=True,
            )
            text = (extracted or "").strip()
        except Exception as exc:  # trafilatura may be absent at runtime
            logger.info("junior browse trafilatura failed: %s", exc)
    if not text:
        try:
            from lxml import html as lxml_html

            text = (lxml_html.fromstring(html).text_content() or "").strip()
        except Exception as exc:
            logger.info("junior browse lxml fallback failed: %s", exc)
    if not text:
        # Last resort: drop tags with a regex. Ugly, but it keeps a mostly
        # text page readable instead of returning nothing.
        text = re.sub(
            r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S
        )
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[ \t]+", " ", text).strip()
    # Collapse the blank-line runs the extractor leaves behind so the voice
    # layer gets tight paragraphs rather than long pauses.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text, title


def fetch_page(url: str) -> PageText:
    """Fetch one public URL and return its readable text.

    Raises PageFetchError with a speakable detail on any failure — the route
    turns that into a 4xx and the client maps it to a spoken line.
    """
    if not is_allowed_url(url):
        raise PageFetchError("I can only open http and https web pages.")
    timeout = httpx.Timeout(
        FETCH_TIMEOUT_SEC,
        connect=FETCH_CONNECT_SEC,
        read=FETCH_TIMEOUT_SEC,
        write=10.0,
        pool=10.0,
    )
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers=HEADERS,
        ) as client:
            with client.stream("GET", url) as response:
                if response.status_code >= 400:
                    raise PageFetchError(
                        f"That page returned an error ({response.status_code})."
                    )
                ctype = (response.headers.get("content-type") or "").lower()
                if ctype and "html" not in ctype and "xml" not in ctype and "text" not in ctype:
                    # A PDF or an image: Junior has no reader for those and
                    # buffering them into text would be garbage.
                    raise PageFetchError("That link isn't a web page I can read.")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_raw():
                    total += len(chunk)
                    if total > MAX_RESPONSE_BYTES:
                        raise PageFetchError("That page is too large to read.")
                    chunks.append(chunk)
                raw = b"".join(chunks)
                encoding = response.encoding
    except PageFetchError:
        raise
    except httpx.TimeoutException:
        raise PageFetchError("That page took too long to load.")
    except httpx.HTTPError as exc:
        raise PageFetchError(f"I couldn't open that page ({type(exc).__name__}).")

    html = raw.decode(encoding or "utf-8", errors="replace")
    text, title = extract_readable_text(html, url)
    if not text.strip():
        raise PageFetchError("That page didn't have any text I could read.")
    logger.info("junior browse url=%s title=%r chars=%s", url, title[:80], len(text))
    return PageText(url=url, title=title, text=text)
