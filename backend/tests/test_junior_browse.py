from __future__ import annotations

import unittest

from app.services.junior_browse import (
    MAX_URL_CHARS,
    PageFetchError,
    extract_readable_text,
    is_allowed_url,
)

ARTICLE_HTML = """
<html><head><title>Senate passes bill</title>
<script>var tracker = 1;</script>
<style>.a { color: red; }</style></head>
<body>
<nav><a href="/">Home</a> <a href="/news">News</a></nav>
<article><h1>Senate passes bill</h1>
<p>The Senate passed the bill on Tuesday after a long debate about the budget.</p>
<p>Members of both parties spoke in favor of the measure before the vote.</p>
<p>The president is expected to sign it into law later this week.</p>
</article>
<footer>Copyright 2026 Newsmax. All rights reserved.</footer>
</body></html>
"""


class JuniorBrowseUrlGateTests(unittest.TestCase):
    """The URL gate is the SSRF boundary in front of a model-driven fetch."""

    def test_public_http_and_https_are_allowed(self):
        self.assertTrue(is_allowed_url("https://www.newsmax.com/us-news"))
        self.assertTrue(is_allowed_url("http://example.com/a"))

    def test_non_http_schemes_are_refused(self):
        for url in (
            "file:///etc/passwd",
            "ftp://example.com/x",
            "gopher://example.com/",
            "javascript:alert(1)",
            "data:text/html,hi",
            "storykeep://notes",
        ):
            self.assertFalse(is_allowed_url(url), url)

    def test_private_and_loopback_hosts_are_refused(self):
        for url in (
            "http://localhost/x",
            "http://127.0.0.1/x",
            "http://10.0.0.5/x",
            "http://192.168.1.1/x",
            "http://172.16.0.1/x",
            "http://172.31.255.255/x",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/x",
        ):
            self.assertFalse(is_allowed_url(url), url)

    def test_public_hosts_that_merely_look_private_are_allowed(self):
        # 172.15 and 172.32 are outside the private range; only 16-31 is blocked.
        self.assertTrue(is_allowed_url("https://172.15.0.1/x"))
        self.assertTrue(is_allowed_url("https://172.32.0.1/x"))

    def test_malformed_and_oversized_urls_are_refused(self):
        self.assertFalse(is_allowed_url(""))
        self.assertFalse(is_allowed_url("   "))
        self.assertFalse(is_allowed_url("https://"))
        self.assertFalse(is_allowed_url("https://exa mple.com/a"))
        self.assertFalse(is_allowed_url("https://example.com/" + "a" * MAX_URL_CHARS))


class JuniorBrowseExtractTests(unittest.TestCase):
    def test_extract_readable_text_returns_prose_title_and_no_scripts(self):
        text, title = extract_readable_text(ARTICLE_HTML, "https://www.newsmax.com/a")
        self.assertEqual(title, "Senate passes bill")
        self.assertIn("The Senate passed the bill on Tuesday", text)
        self.assertNotIn("tracker", text, "script bodies must not survive extraction")
        self.assertNotIn("color: red", text, "style blocks must not survive extraction")
        self.assertNotIn("Copyright 2026", text, "footer boilerplate is dropped")

    def test_extract_readable_text_never_raises_on_junk(self):
        for html in ("", "   ", "<<<>>>", "<html><body></body></html>", "not html at all"):
            text, _title = extract_readable_text(html, "https://x.com/a")
            self.assertIsInstance(text, str)

    def test_extract_readable_text_falls_back_when_no_article_node(self):
        text, _title = extract_readable_text(
            "<html><body><p>Just a plain paragraph of readable prose here.</p></body></html>",
            "https://x.com/a",
        )
        self.assertIn("Just a plain paragraph of readable prose", text)

    def test_fetch_page_refuses_a_disallowed_url_before_any_request(self):
        # The gate raises PageFetchError (no network touched) for a private host.
        from app.services import junior_browse

        with self.assertRaises(PageFetchError) as ctx:
            junior_browse.fetch_page("http://169.254.169.254/latest/meta-data/")
        self.assertIn("http and https", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
