from __future__ import annotations

import unittest
import unittest.mock

from types import SimpleNamespace

from app.services.extractor import ExtractFailedError, _clean_text, _extract_usable, extract_html, fill_article


BLAZE_STYLE = """
<html><head><style>
.widget { box-sizing: border-box; margin: 0; padding: 0; }
#footer-nav { display: flex; }
@media (max-width: 768px) { .sidebar { display:none; } }
</style></head><body>
<nav class="site-nav">Home | News | Politics</nav>
<div class="cookie-banner">We use cookies to improve your experience.</div>
<article>
<h1>Policy Shift Shakes Capitol</h1>
<div itemprop="articleBody">
<p>Congress moved Tuesday on a surprise package that could reshape spending for years.</p>
<p>Analysts said the vote reflected months of quiet negotiation behind closed doors.</p>
</div>
</article>
<aside class="related-widget">Related stories you might like</aside>
<footer class="site-footer">Copyright Blaze Media All rights reserved.</footer>
<div class="author-bio">Jane Reporter covers politics for Blaze News.</div>
<div class="author-bio">Jane Reporter covers politics for Blaze News.</div>
<div class="newsletter-signup">Subscribe to our newsletter for daily updates.</div>
</body></html>
"""


class ExtractorTests(unittest.TestCase):
    def test_blaze_style_page_starts_at_lede_without_css(self):
        html, text = extract_html(BLAZE_STYLE, "https://example.com/blaze-story")
        self.assertIsNotNone(text)
        assert text is not None
        self.assertTrue(text.startswith("Congress moved Tuesday"))
        self.assertIn("Analysts said", text)
        self.assertNotIn("box-sizing", text.lower())
        self.assertNotIn(".widget", text)
        self.assertNotIn("cookie", text.lower())
        self.assertNotIn("Subscribe to our newsletter", text)
        self.assertNotIn("Related stories", text)
        self.assertNotIn("Jane Reporter covers politics", text)
        if html:
            self.assertNotIn("<style", html.lower())
            self.assertNotIn("box-sizing", html.lower())

    def test_clean_text_drops_css_lines(self):
        raw = "\n".join(
            [
                ".widget{margin:0;padding:0;box-sizing:border-box;}",
                "#footer{display:flex;}",
                "Actual paragraph one.",
                "Actual paragraph one.",
                "Actual paragraph two.",
            ]
        )
        cleaned = _clean_text(raw)
        self.assertIn("Actual paragraph one.", cleaned)
        self.assertIn("Actual paragraph two.", cleaned)
        self.assertNotIn(".widget", cleaned)
        self.assertNotIn("box-sizing", cleaned)
        self.assertEqual(cleaned.count("Actual paragraph one."), 1)


    def test_extract_usable_rejects_css_only(self):
        css_only = ".widget{margin:0;padding:0;box-sizing:border-box;}\n#footer{display:flex;}"
        self.assertFalse(_extract_usable("<style>.widget{}</style>", css_only))

    def test_extract_image_reads_og_image(self):
        html = """
        <html><head>
        <meta property="og:image" content="https://cdn.example.com/hero.jpg" />
        </head><body><article><p>Story body.</p></article></body></html>
        """
        from app.services.extractor import _extract_image

        image = _extract_image(html, "https://example.com/story")
        self.assertEqual(image, "https://cdn.example.com/hero.jpg")

    def test_repair_display_body_strips_polluted_html(self):
        from app.services.extractor import repair_display_body

        html, text = extract_html(BLAZE_STYLE, "https://example.com/blaze-story")
        assert text is not None
        repaired_text, repaired_html = repair_display_body(html, None)
        self.assertIsNotNone(repaired_text)
        assert repaired_text is not None
        self.assertIn("Congress moved Tuesday", repaired_text)
        self.assertNotIn("box-sizing", (repaired_html or "").lower())

    def test_html_pollution_rejected(self):
        from app.services.extractor import _html_is_polluted

        self.assertTrue(_html_is_polluted("<style>.widget{}</style><p>Hi</p>"))
        self.assertTrue(_html_is_polluted("<p>.widget{margin:0;box-sizing:border-box;}</p>"))

    def test_fill_article_keeps_previous_body_on_failed_force_extract(self):
        article = SimpleNamespace(
            url="https://example.com/story",
            content_html="<p>Old body kept.</p>",
            content_text="Old body kept.",
            fetched_at=None,
        )

        class FakeDb:
            def add(self, _obj) -> None:
                return None

        with unittest.mock.patch("app.services.extractor.extract_url", return_value=(None, None, None)):
            with self.assertRaises(ExtractFailedError):
                fill_article(FakeDb(), article, force=True)  # type: ignore[arg-type]
        self.assertEqual(article.content_text, "Old body kept.")


if __name__ == "__main__":
    unittest.main()
