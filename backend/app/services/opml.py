from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any
from xml.sax.saxutils import escape


def parse_opml(raw: str) -> list[dict[str, str | None]]:
    text = (raw or "").strip()
    if not text:
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"OPML could not be parsed: {exc}") from exc

    found: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for outline in root.iter("outline"):
        url = (
            outline.attrib.get("xmlUrl")
            or outline.attrib.get("xmlurl")
            or outline.attrib.get("xmlURL")
            or ""
        ).strip()
        if not url or url in seen:
            continue
        seen.add(url)
        title = (outline.attrib.get("title") or outline.attrib.get("text") or "").strip() or None
        found.append({"url": url, "title": title})
    return found


def build_opml(feeds: list[Any]) -> str:
    outlines = []
    for feed in feeds:
        title = escape(feed.title or feed.url or "Feed")
        url = escape(feed.url or "")
        html = escape(feed.site_url or feed.url or "")
        outlines.append(
            f'    <outline type="rss" text="{title}" title="{title}" xmlUrl="{url}" htmlUrl="{html}" />'
        )
    body = "\n".join(outlines)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<opml version="2.0">\n'
        "  <head>\n"
        "    <title>Storykeep subscriptions</title>\n"
        "  </head>\n"
        "  <body>\n"
        f"{body}\n"
        "  </body>\n"
        "</opml>\n"
    )
