from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx

from app.services import rss
from app.services.rss import (
    NO_RSS_ITEMS,
    PUBLISHER_BLOCKED,
    FeedFetchError,
    count_xml_items,
    entries_from_xml,
    fetch_feed_document,
    parse_feed_body,
    refresh_feed,
)

NEWSMAX = "https://www.newsmax.com/rss/US/18/"
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<title>US</title>
<item><title>One</title><link>https://www.newsmax.com/one</link><guid>https://www.newsmax.com/one</guid></item>
<item><title>Two</title><link>https://www.newsmax.com/two</link><guid>https://www.newsmax.com/two</guid></item>
</channel></rss>"""
ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>E</title><id>e1</id><link href="https://example.com/e"/></entry>
</feed>"""
HTML = b"<!DOCTYPE html><html><body>homepage</body></html>"


class FakeResponse:
    def __init__(self, status_code=200, content=b"", content_type="application/rss+xml", url=NEWSMAX):
        self.status_code = status_code
        self.content = content
        self.headers = {"content-type": content_type, "ETag": "w/1"}
        self.encoding = "utf-8"
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=MagicMock(), response=MagicMock(status_code=self.status_code))


class RssFetchTests(unittest.TestCase):
    def test_counts_item_and_entry_tags(self):
        self.assertEqual(count_xml_items(RSS), 2)
        self.assertEqual(count_xml_items(ATOM), 1)
        self.assertEqual(count_xml_items(HTML), 0)
        self.assertEqual(count_xml_items(b""), 0)

    def test_xml_fallback_parses_item_and_entry(self):
        items = entries_from_xml(RSS)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["title"], "One")
        atom = entries_from_xml(ATOM)
        self.assertEqual(atom[0]["link"], "https://example.com/e")
        parsed = parse_feed_body(RSS)
        self.assertEqual(len(parsed.entries), 2)

    def test_rss_items_are_recorded_on_health_snapshot(self):
        with patch("app.services.rss._get_feed_response", return_value=FakeResponse(content=RSS)):
            doc = fetch_feed_document(NEWSMAX)
        self.assertEqual(doc.item_count, 2)
        self.assertIsNone(doc.error)
        snap = rss.last_fetch_snapshot()
        self.assertEqual(snap["status"], 200)
        self.assertEqual(snap["bytes"], len(RSS))
        self.assertEqual(snap["item_count"], 2)

    def test_html_or_empty_is_no_rss_items(self):
        with patch("app.services.rss._get_feed_response", return_value=FakeResponse(content=HTML, content_type="text/html")):
            with self.assertRaises(FeedFetchError) as raised:
                fetch_feed_document(NEWSMAX)
        self.assertEqual(str(raised.exception), NO_RSS_ITEMS)
        self.assertEqual(rss.last_fetch_snapshot()["item_count"], 0)

        with patch("app.services.rss._get_feed_response", return_value=FakeResponse(content=b"  ")):
            with self.assertRaises(FeedFetchError) as raised:
                fetch_feed_document(NEWSMAX)
        self.assertEqual(str(raised.exception), NO_RSS_ITEMS)

    def test_forbidden_is_publisher_blocked(self):
        with patch("app.services.rss._get_feed_response", return_value=FakeResponse(status_code=403, content=b"denied")):
            with self.assertRaises(FeedFetchError) as raised:
                fetch_feed_document(NEWSMAX)
        self.assertEqual(str(raised.exception), PUBLISHER_BLOCKED)

    def test_timeout_retries_twice_then_blocked(self):
        calls = {"n": 0}

        def fake_client(_timeout, _headers):
            calls["n"] += 1
            raise httpx.ReadTimeout("The read operation timed out")

        with patch("app.services.rss._http11_client", side_effect=fake_client):
            with self.assertRaises(FeedFetchError) as raised:
                fetch_feed_document(NEWSMAX)
        self.assertEqual(str(raised.exception), PUBLISHER_BLOCKED)
        self.assertEqual(calls["n"], 1 + rss.FETCH_TIMEOUT_RETRIES)
        self.assertEqual(rss.last_fetch_snapshot()["status"], "timeout")

    def test_refresh_keeps_feed_row_and_sets_error(self):
        feed = SimpleNamespace(
            id=uuid4(),
            url=NEWSMAX,
            etag=None,
            last_modified=None,
            last_error=None,
            last_fetched_at=None,
            user_id=uuid4(),
            title="Newsmax",
        )
        db = MagicMock()
        with patch(
            "app.services.rss.fetch_feed_document",
            side_effect=FeedFetchError(NO_RSS_ITEMS, status=200, nbytes=120),
        ):
            created = refresh_feed(db, feed, extract=False)
        self.assertEqual(created, 0)
        self.assertEqual(feed.last_error, NO_RSS_ITEMS)
        db.delete.assert_not_called()
        db.add.assert_called()
        db.commit.assert_called()

    def test_does_not_scrape_newsmax_homepage(self):
        with patch("app.services.rss._get_feed_response") as getter:
            self.assertEqual(rss.discover_feeds("https://www.newsmax.com/"), [])
            getter.assert_not_called()

    def test_ingest_source_never_mentions_code_interpreter(self):
        from pathlib import Path

        text = Path(rss.__file__).read_text(encoding="utf-8")
        self.assertNotIn("code_interpreter", text)
        self.assertNotIn("complete_once", text)
        self.assertIn("http2=False", text)

    def test_browser_accept_and_http11(self):
        self.assertIn("application/rss+xml", rss.HEADERS["Accept"])
        self.assertIn("Mozilla", rss.HEADERS["User-Agent"])
        self.assertEqual(rss.FETCH_TIMEOUT_SEC, 20.0)
        self.assertEqual(rss.FETCH_TIMEOUT_RETRIES, 2)


if __name__ == "__main__":
    unittest.main()
