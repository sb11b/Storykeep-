from __future__ import annotations

import unittest

from app.services.extractor import _clean_text, extract_html


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


if __name__ == "__main__":
    unittest.main()
