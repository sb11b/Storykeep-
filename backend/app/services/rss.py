from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import mktime
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import UUID
from xml.etree import ElementTree as ET

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, Feed
from app.services import changelog, extractor
from app.config import settings

logger = logging.getLogger(__name__)

# Browser-like GET. Ingest is HTTP only — no xAI tools.
FETCH_TIMEOUT_SEC = 20.0
FETCH_TIMEOUT_RETRIES = 2
FETCH_BUDGET_SEC = 45.0
NO_RSS_ITEMS = "Feed returned no RSS items"
PUBLISHER_BLOCKED = "publisher blocked bot"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
    "Accept-Language": "en-US,en;q=0.9",
}
BLOCK_STATUSES = {401, 403, 406, 429, 451}
_LAST_FETCH: dict[str, object] = {}
_LAST_FETCH_FILE = "last-rss-fetch.json"


def _fetch_file() -> Path:
    return settings.data_dir / _LAST_FETCH_FILE


def last_fetch_snapshot() -> dict[str, object]:
    if _LAST_FETCH:
        return dict(_LAST_FETCH)
    path = _fetch_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {}


def _record_fetch(*, status: int | str | None, nbytes: int, item_count: int, url: str) -> None:
    payload = {
        "status": status,
        "bytes": nbytes,
        "item_count": item_count,
        "url": url,
    }
    _LAST_FETCH.clear()
    _LAST_FETCH.update(payload)
    logger.info("rss_fetch %s", payload)
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        _fetch_file().write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def _entry_datetime(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
            except Exception:
                pass
    for key in ("published", "updated"):
        raw = entry.get(key)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            continue
    return None


def _looks_like_image_url(url: str, mime: str = "") -> bool:
    if mime.startswith("image"):
        return True
    return bool(re.search(r"\.(jpe?g|png|gif|webp|avif|bmp)(\?|$)", url, re.I))


def _entry_image(entry: Any, base_url: str = "") -> str | None:
    """First usable image for a feed entry, resolved against the entry link."""
    candidate = _entry_image_candidate(entry)
    if not candidate:
        return None
    resolved = urljoin(base_url or str(entry.get("link") or ""), candidate.strip())
    return resolved[:2000] or None


def _entry_image_candidate(entry: Any) -> str | None:
    if entry.get("image", {}).get("href"):
        return entry["image"]["href"]
    for media in entry.get("media_content", []) or []:
        url = media.get("url")
        if not url:
            continue
        medium = str(media.get("medium", "")).lower()
        mime = str(media.get("type", "")).lower()
        if medium == "image" or _looks_like_image_url(url, mime):
            return url
    for thumb in entry.get("media_thumbnail", []) or []:
        url = thumb.get("url")
        if url:
            return url
    for link in entry.get("links", []) or []:
        if str(link.get("type", "")).startswith("image") and link.get("href"):
            return link["href"]
    for enclosure in entry.get("enclosures", []) or []:
        href = enclosure.get("href")
        if not href:
            continue
        mime = str(enclosure.get("type", "")).lower()
        if mime.startswith("image") or _looks_like_image_url(href, mime):
            return href
    return None


def entry_image_for(entry: Any, url: str, feed_html: str | None, stored_html: str | None) -> str | None:
    """media:content / thumbnail / enclosure, then the first image in the entry body."""
    image_url = _entry_image(entry, url)
    if image_url:
        return image_url
    return extractor._first_content_image(feed_html or stored_html or "", url)


def _entry_html(entry: Any) -> str | None:
    for content in entry.get("content", []) or []:
        if content.get("value"):
            return content["value"]
    return entry.get("summary")


def refetch_entry_html(db: Session, article: Article) -> str | None:
    feed = db.get(Feed, article.feed_id)
    if not feed:
        return None
    try:
        parsed = fetch_feed_document(feed.url, feed.etag, feed.last_modified).parsed
    except Exception as exc:
        logger.info("refetch feed failed %s: %s", feed.url, exc)
        return None
    if parsed is None:
        return None
    target_guid = article.guid
    target_url = article.url
    for entry in parsed.entries:
        guid = str(entry.get("id") or entry.get("link") or entry.get("title") or "")
        url = str(entry.get("link") or "")
        if guid == target_guid or url == target_url:
            return _entry_html(entry)
    return None


COMMON_FEED_PATHS = (
    "/feed",
    "/rss",
    "/rss.xml",
    "/atom.xml",
    "/feed.xml",
    "/index.xml",
    "/feeds/posts/default",
)


def _looks_like_feed(parsed: Any) -> bool:
    if parsed is None:
        return False
    if parsed.entries:
        return True
    feed = parsed.feed or {}
    if feed.get("title") and (feed.get("link") or feed.get("subtitle")):
        return True
    version = str(getattr(parsed, "version", "") or "")
    return bool(version)


def discover_feeds(site_url: str) -> list[dict[str, str | None]]:
    url = site_url.strip()
    if not url:
        return []
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    headers = dict(HEADERS)
    candidates: list[dict[str, str | None]] = []
    seen: set[str] = set()

    def add(href: str, title: str | None = None, kind: str | None = None) -> None:
        href = href.strip()
        if not href or href in seen:
            return
        seen.add(href)
        candidates.append({"url": href, "title": title, "kind": kind})

    if _is_newsmax_host(url) and not _looks_like_feed_path(url):
        logger.info("rss_fetch skip homepage scrape %s", url)
        return []

    try:
        response = _get_feed_response(url, headers=headers)
        response.raise_for_status()
        body = response.content
        final_url = str(response.url)
        content_type = (response.headers.get("content-type") or "").lower()
        encoding = response.encoding or "utf-8"
    except Exception as exc:
        logger.info("discover fetch failed %s: %s", url, exc)
        raise ValueError(f"Could not fetch {url}") from exc

    parsed = feedparser.parse(body)
    if _looks_like_feed(parsed) and (
        "xml" in content_type or "rss" in content_type or "atom" in content_type or parsed.entries
    ):
        add(final_url, parsed.feed.get("title"), "feed")
        return candidates

    html = body.decode(encoding, errors="replace")
    for match in re.finditer(r"<link\b[^>]*>", html, re.I):
        tag = match.group(0)
        rel = _attr(tag, "rel").lower()
        typ = _attr(tag, "type").lower()
        href = _attr(tag, "href")
        title = _attr(tag, "title") or None
        if not href:
            continue
        absolute = urljoin(final_url, href)
        if any(token in typ for token in ("rss", "atom", "xml")) or any(
            token in rel for token in ("alternate", "feed", "rss", "atom")
        ):
            if "rss" in typ or "atom" in typ or "xml" in typ or "feed" in rel or "rss" in rel or "atom" in rel:
                kind = "atom" if "atom" in typ else "rss"
                add(absolute, title, kind)

    parsed_url = urlparse(final_url)
    origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
    extras: list[str] = []
    for path in COMMON_FEED_PATHS:
        extras.append(urljoin(origin + "/", path.lstrip("/")))
    for extra in extras:
        if extra in seen:
            continue
        try:
            probe = _get_feed_response(extra, headers=headers, timeout_sec=8.0, retries=0)
            if probe.status_code >= 400:
                continue
            probed = feedparser.parse(probe.content)
            if _looks_like_feed(probed):
                add(str(probe.url), probed.feed.get("title"), "feed")
        except Exception:
            continue
        if len(candidates) >= 8:
            break

    return candidates


def _attr(tag: str, name: str) -> str:
    match = re.search(rf"""{name}\s*=\s*["']([^"']+)["']""", tag, re.I)
    if match:
        return match.group(1).strip()
    match = re.search(rf"""{name}\s*=\s*([^\s>]+)""", tag, re.I)
    return match.group(1).strip() if match else ""


def _is_newsmax_host(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower().removeprefix("www.")
    return host == "newsmax.com"


def _looks_like_feed_path(url: str) -> bool:
    path = (urlparse(url).path or "").lower()
    return any(token in path for token in ("/rss", "/feed", "/atom", ".xml"))


def _xml_local(tag: str) -> str:
    return tag.split("}", 1)[-1].lower()


def _body_is_html(content_type: str, body: bytes) -> bool:
    ct = (content_type or "").lower()
    if "html" in ct and "xml" not in ct:
        return True
    head = body.lstrip()[:240].lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html")


def _publisher_blocked(status: int | None, body: bytes) -> bool:
    if status in BLOCK_STATUSES:
        return True
    sample = body[:8000].lower()
    needles = (
        b"access denied",
        b"captcha",
        b"cf-ray",
        b"pardon our interruption",
        b"blocked",
        b"bot detected",
        b"enable javascript",
    )
    return bool(status and status >= 400 and any(token in sample for token in needles))


def count_xml_items(body: bytes) -> int:
    if not body:
        return 0
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        return 0
    return len(re.findall(r"<(?:item|entry)\b", text, flags=re.I))


def entries_from_xml(body: bytes) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    out: list[dict[str, Any]] = []
    for node in root.iter():
        if _xml_local(node.tag) not in {"item", "entry"}:
            continue
        rec: dict[str, Any] = {}
        for child in list(node):
            name = _xml_local(child.tag)
            text = (child.text or "").strip()
            href = (child.get("href") or "").strip()
            if name == "title" and text:
                rec["title"] = text
            elif name == "link":
                rec["link"] = text or href
            elif name in {"id", "guid"} and text:
                rec["id"] = text
            elif name in {"summary", "description"} and text:
                rec["summary"] = text
            elif name in {"published", "updated", "pubdate"} and text:
                rec["published"] = text
        if rec.get("link") or rec.get("id") or rec.get("title"):
            out.append(rec)
    return out


def parse_feed_body(body: bytes) -> Any:
    parsed = feedparser.parse(body)
    if parsed.entries:
        return parsed
    xml_entries = entries_from_xml(body)
    if xml_entries:
        parsed.entries = xml_entries
        parsed.bozo = 0
    return parsed


def _http11_client(timeout_sec: float, headers: dict[str, str]) -> httpx.Client:
    return httpx.Client(
        http2=False,
        timeout=httpx.Timeout(timeout_sec, connect=min(10.0, timeout_sec), read=timeout_sec, write=10.0, pool=5.0),
        follow_redirects=True,
        headers=headers,
    )


def _get_feed_response(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_sec: float = FETCH_TIMEOUT_SEC,
    retries: int = FETCH_TIMEOUT_RETRIES,
) -> httpx.Response:
    """HTTP/1.1 GET. Retry timeouts only. Never waits past FETCH_BUDGET_SEC (avoid 504)."""
    hdrs = dict(headers or HEADERS)
    last_exc: Exception | None = None
    started = time.monotonic()
    attempts = 1 + max(0, retries)
    for attempt in range(attempts):
        remaining = FETCH_BUDGET_SEC - (time.monotonic() - started)
        if remaining < 1:
            break
        attempt_timeout = min(timeout_sec, remaining)
        try:
            with _http11_client(attempt_timeout, hdrs) as client:
                return client.get(url)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            logger.info(
                "rss_fetch retry url=%s attempt=%s err=%s",
                url,
                attempt + 1,
                type(exc).__name__,
            )
            continue
    if last_exc:
        raise last_exc
    raise httpx.TimeoutException("Feed fetch timed out")


@dataclass
class FeedDocument:
    parsed: Any | None
    etag: str | None = None
    last_modified: str | None = None
    status: int | str | None = None
    nbytes: int = 0
    item_count: int = 0
    error: str | None = None


def fetch_feed_document(url: str, etag: str | None = None, last_modified: str | None = None) -> FeedDocument:
    headers = dict(HEADERS)
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    try:
        response = _get_feed_response(url, headers=headers)
    except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as exc:
        _record_fetch(status="timeout", nbytes=0, item_count=0, url=url)
        raise FeedFetchError(PUBLISHER_BLOCKED, status="timeout", nbytes=0) from exc

    status = response.status_code
    body = response.content or b""
    nbytes = len(body)

    if status == 304:
        _record_fetch(status=304, nbytes=0, item_count=0, url=url)
        return FeedDocument(parsed=None, etag=etag, last_modified=last_modified, status=304, nbytes=0, item_count=0)

    if _publisher_blocked(status, body):
        _record_fetch(status=status, nbytes=nbytes, item_count=0, url=url)
        raise FeedFetchError(PUBLISHER_BLOCKED, status=status, nbytes=nbytes)

    if status >= 400:
        _record_fetch(status=status, nbytes=nbytes, item_count=0, url=url)
        raise FeedFetchError(NO_RSS_ITEMS, status=status, nbytes=nbytes)

    content_type = response.headers.get("content-type") or ""
    if not body.strip() or _body_is_html(content_type, body):
        _record_fetch(status=status, nbytes=nbytes, item_count=0, url=url)
        raise FeedFetchError(NO_RSS_ITEMS, status=status, nbytes=nbytes)

    parsed = parse_feed_body(body)
    items = list(parsed.entries or [])
    xml_count = count_xml_items(body)
    item_count = max(len(items), xml_count)
    _record_fetch(status=status, nbytes=nbytes, item_count=item_count, url=url)
    if item_count == 0:
        return FeedDocument(
            parsed=parsed,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            status=status,
            nbytes=nbytes,
            item_count=0,
            error=NO_RSS_ITEMS,
        )
    return FeedDocument(
        parsed=parsed,
        etag=response.headers.get("ETag"),
        last_modified=response.headers.get("Last-Modified"),
        status=status,
        nbytes=nbytes,
        item_count=item_count,
    )


class FeedFetchError(Exception):
    def __init__(self, message: str, *, status: int | str | None = None, nbytes: int = 0) -> None:
        super().__init__(message)
        self.status = status
        self.nbytes = nbytes


def refresh_feed(db: Session, feed: Feed, extract: bool = True, limit: int = 50) -> int:
    try:
        document = fetch_feed_document(feed.url, feed.etag, feed.last_modified)
    except FeedFetchError as exc:
        feed.last_error = str(exc)[:500]
        feed.last_fetched_at = datetime.now(timezone.utc)
        db.add(feed)
        db.commit()
        return 0
    except Exception as exc:
        feed.last_error = str(exc)[:500]
        feed.last_fetched_at = datetime.now(timezone.utc)
        db.add(feed)
        db.commit()
        logger.info("feed fetch failed %s: %s", feed.url, exc)
        return 0

    parsed = document.parsed
    etag = document.etag
    last_modified = document.last_modified

    if document.error:
        feed.last_error = document.error[:500]
        feed.last_fetched_at = datetime.now(timezone.utc)
        db.add(feed)
        db.commit()
        return 0

    if parsed is None:
        feed.last_fetched_at = datetime.now(timezone.utc)
        db.add(feed)
        db.commit()
        return 0

    if getattr(parsed, "bozo", False) and not parsed.entries:
        feed.last_error = NO_RSS_ITEMS
        feed.last_fetched_at = datetime.now(timezone.utc)
        db.add(feed)
        db.commit()
        return 0

    feed.etag = etag
    feed.last_modified = last_modified
    feed.last_error = None
    feed.last_fetched_at = datetime.now(timezone.utc)
    if parsed.feed.get("title"):
        feed.title = parsed.feed.get("title")
    if parsed.feed.get("subtitle"):
        feed.description = parsed.feed.get("subtitle")
    if parsed.feed.get("link"):
        feed.site_url = parsed.feed.get("link")
    icon = parsed.feed.get("icon") or parsed.feed.get("logo")
    if icon:
        feed.favicon_url = icon

    created = 0
    for entry in parsed.entries[:limit]:
        guid = str(entry.get("id") or entry.get("link") or entry.get("title") or "")
        url = str(entry.get("link") or "")
        title = (entry.get("title") or "Untitled").strip()
        if not guid or not url:
            continue
        existing = db.scalar(select(Article).where(Article.feed_id == feed.id, Article.guid == guid))
        if existing:
            # Backfill art for rows stored before image extraction improved.
            if not existing.image_url:
                stored_html = _entry_html(entry)
                backfilled = entry_image_for(entry, existing.url or url, stored_html, existing.feed_html)
                if backfilled:
                    existing.image_url = backfilled
                    db.add(existing)
            continue
        feed_html = _entry_html(entry)
        feed_store_html, feed_store_text = extractor._feed_storage_body(feed_html, entry.get("summary"))
        image_url = entry_image_for(entry, url, feed_html, feed_store_html)
        article = Article(
            feed_id=feed.id,
            guid=guid[:2000],
            url=url[:4000],
            title=title[:500],
            author=entry.get("author"),
            published_at=_entry_datetime(entry),
            summary=entry.get("summary"),
            feed_html=feed_html or feed_store_html,
            feed_text=feed_store_text,
            content_html=None,
            content_text=None,
            image_url=image_url,
        )
        db.add(article)
        db.flush()
        if extract:
            extractor.fill_article(db, article, force=False)
        changelog.record(db, feed.user_id, "article", article.id, "upsert", {"title": article.title})
        created += 1

    db.add(feed)
    db.commit()
    return created


def refresh_user_feeds(db: Session, user_id: UUID, extract: bool = True) -> int:
    feeds = db.scalars(select(Feed).where(Feed.user_id == user_id, Feed.is_active.is_(True))).all()
    total = 0
    for feed in feeds:
        total += refresh_feed(db, feed, extract=extract)
    return total
