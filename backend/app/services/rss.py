from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import mktime
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import UUID

import feedparser
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, Feed
from app.services import changelog, extractor

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Storykeep/1.0 (+https://localhost; personal archive reader)"
}


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


def _entry_image(entry: Any) -> str | None:
    if entry.get("image", {}).get("href"):
        return entry["image"]["href"]
    for media in entry.get("media_content", []) or []:
        if media.get("url") and str(media.get("type", "")).startswith("image"):
            return media["url"]
    for link in entry.get("links", []) or []:
        if str(link.get("type", "")).startswith("image") and link.get("href"):
            return link["href"]
    for enclosure in entry.get("enclosures", []) or []:
        if enclosure.get("href") and str(enclosure.get("type", "")).startswith("image"):
            return enclosure["href"]
    return None


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
        parsed, _, _ = fetch_feed_document(feed.url, feed.etag, feed.last_modified)
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

    try:
        with httpx.Client(timeout=18.0, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
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
            with httpx.Client(timeout=8.0, follow_redirects=True, headers=headers) as client:
                probe = client.get(extra)
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


def fetch_feed_document(url: str, etag: str | None = None, last_modified: str | None = None) -> tuple[Any, str | None, str | None]:
    headers = dict(HEADERS)
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    with httpx.Client(timeout=25.0, follow_redirects=True, headers=headers) as client:
        response = client.get(url)
        if response.status_code == 304:
            return None, etag, last_modified
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        return parsed, response.headers.get("ETag"), response.headers.get("Last-Modified")


def refresh_feed(db: Session, feed: Feed, extract: bool = True, limit: int = 50) -> int:
    try:
        parsed, etag, last_modified = fetch_feed_document(feed.url, feed.etag, feed.last_modified)
    except Exception as exc:
        feed.last_error = str(exc)[:500]
        feed.last_fetched_at = datetime.now(timezone.utc)
        db.add(feed)
        db.commit()
        logger.info("feed fetch failed %s: %s", feed.url, exc)
        return 0

    if parsed is None:
        feed.last_fetched_at = datetime.now(timezone.utc)
        feed.last_error = None
        db.add(feed)
        db.commit()
        return 0

    if getattr(parsed, "bozo", False) and not parsed.entries:
        feed.last_error = str(getattr(parsed, "bozo_exception", "Could not parse feed"))[:500]
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
            continue
        feed_html = _entry_html(entry)
        feed_body_html, feed_body_text = extractor._prepare_feed_body(feed_html, entry.get("summary"))
        article = Article(
            feed_id=feed.id,
            guid=guid[:2000],
            url=url[:4000],
            title=title[:500],
            author=entry.get("author"),
            published_at=_entry_datetime(entry),
            summary=entry.get("summary"),
            feed_html=feed_html,
            feed_text=feed_body_text,
            content_html=feed_body_html,
            content_text=feed_body_text,
            image_url=_entry_image(entry),
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
