from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
import trafilatura
from readability import Document
from sqlalchemy.orm import Session

from app.models import Article

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Storykeep/1.0 (+https://localhost; personal archive reader)"
}


def extract_url(url: str) -> tuple[str | None, str | None]:
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=HEADERS) as client:
            response = client.get(url)
            response.raise_for_status()
            html = response.text
    except Exception as exc:
        logger.info("extract fetch failed %s: %s", url, exc)
        return None, None

    downloaded = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=True,
        output_format="html",
        url=url,
    )
    text = trafilatura.extract(html, include_comments=False, include_tables=True, url=url)
    if downloaded and text:
        return downloaded, text

    try:
        doc = Document(html)
        cleaned = doc.summary()
        plain = Document(html).summary(html_partial=True)
        fallback_text = trafilatura.extract(cleaned) or _strip_tags(cleaned)
        return cleaned or None, fallback_text or _strip_tags(plain)
    except Exception as exc:
        logger.info("readability failed %s: %s", url, exc)
        return None, None


def _strip_tags(html: str) -> str:
    try:
        from lxml import html as lxml_html

        return lxml_html.fromstring(html).text_content().strip()
    except Exception:
        return html


def extract_page(url: str) -> tuple[str | None, str | None, str | None]:
    html, text = extract_url(url)
    title = None
    source = html or ""
    if source:
        try:
            from lxml import html as lxml_html

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
