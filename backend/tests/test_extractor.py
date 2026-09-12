from __future__ import annotations

import unittest
import unittest.mock

from types import SimpleNamespace

from app.services.extractor import (
    CHROME_NOTICE,
    FULL_TEXT_UNAVAILABLE,
    ExtractFailedError,
    _clean_text,
    _extract_usable,
    _html_extract_candidate_valid,
    _is_dek_only,
    extract_html,
    fill_article,
    pick_display_body,
)


BLAZE_LEDE = (
    "Congress moved Tuesday on a surprise package that could reshape spending for years to come, "
    "drawing support from both parties after months of quiet negotiation behind closed doors. "
    "Leaders said the final language would be scrutinized in committee hearings next week."
)
BLAZE_SECOND = (
    "Analysts said the vote reflected a broader realignment in fiscal policy and could influence "
    "how lawmakers approach entitlement reform, defense budgets, and emergency spending this fall. "
    "Several governors said the package would also shape state budget forecasts for the next cycle."
)

BLAZE_TIP_JAR = f"""
<html><body>
<article>
<h1>Policy Shift Shakes Capitol</h1>
<div class="article__body">
<p>{BLAZE_LEDE}</p>
<p>{BLAZE_SECOND}</p>
</div>
<div class="tip-jar support-us">
<p>Want to leave a tip?</p>
<p>Support Us</p>
</div>
</article>
</body></html>
"""


BLAZE_STYLE = (
    """
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
<p>"""
    + BLAZE_LEDE
    + """</p>
<p>"""
    + BLAZE_SECOND
    + """</p>
</div>
</article>
<aside class="related-widget">Related stories you might like</aside>
<footer class="site-footer">Copyright Blaze Media All rights reserved.</footer>
<div class="author-bio">Jane Reporter covers politics for Blaze News.</div>
<div class="author-bio">Jane Reporter covers politics for Blaze News.</div>
<div class="newsletter-signup">Subscribe to our newsletter for daily updates.</div>
</body></html>
"""
)


class ExtractorTests(unittest.TestCase):
    def test_blaze_tip_jar_extracts_article_not_cta(self):
        html, text = extract_html(BLAZE_TIP_JAR, "https://example.com/blaze-story")
        self.assertIsNotNone(text)
        assert text is not None
        self.assertIn("Congress moved Tuesday", text)
        self.assertNotIn("leave a tip", text.lower())
        self.assertNotIn("Support Us", text)
        self.assertFalse(_extract_usable(html, "Want to leave a tip?\nSupport Us"))

    def test_repair_display_body_fixes_cta_only_text_from_html(self):
        from app.services.extractor import repair_display_body

        repaired_text, repaired_html = repair_display_body(BLAZE_TIP_JAR, "Want to leave a tip?\nSupport Us")
        self.assertIsNotNone(repaired_text)
        assert repaired_text is not None
        self.assertIn("Congress moved Tuesday", repaired_text)
        self.assertNotIn("<p>", repaired_text)
        self.assertNotIn("leave a tip", repaired_text.lower())
        self.assertIsNotNone(repaired_html)
        assert repaired_html is not None
        self.assertIn("<p>", repaired_html)

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

    def test_extract_meta_image_reads_twitter_image(self):
        from app.services.extractor import _extract_meta_image

        html = """
        <html><head>
        <meta name="twitter:image" content="https://static.foxnews.com/hero.jpg" />
        </head><body></body></html>
        """
        image = _extract_meta_image(html, "https://www.foxnews.com/politics/example")
        self.assertEqual(image, "https://static.foxnews.com/hero.jpg")

    def test_first_content_image_resolves_relative_url(self):
        from app.services.extractor import _first_content_image

        html = '<div><img src="/images/story.jpg" alt="" /></div>'
        image = _first_content_image(html, "https://www.foxnews.com/politics/example")
        self.assertEqual(image, "https://www.foxnews.com/images/story.jpg")

    def test_ensure_article_image_backfills_from_page_meta(self):
        from app.services.extractor import ensure_article_image
        from types import SimpleNamespace

        article = SimpleNamespace(
            url="https://www.foxnews.com/politics/example",
            image_url=None,
        )
        html = """
        <html><head>
        <meta property="og:image" content="https://static.foxnews.com/hero.jpg" />
        </head><body></body></html>
        """

        class FakeDb:
            def add(self, _obj) -> None:
                return None

        with unittest.mock.patch("app.services.extractor._fetch_html", return_value=html):
            updated = ensure_article_image(FakeDb(), article)  # type: ignore[arg-type]
        self.assertTrue(updated)
        self.assertEqual(article.image_url, "https://static.foxnews.com/hero.jpg")

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

    def test_pick_display_body_prefers_feed_over_chrome_page(self):
        feed_html = "<p>Congress moved Tuesday on a surprise package that could reshape spending for years.</p><p>Analysts said the vote reflected months of quiet negotiation behind closed doors.</p>"
        feed_text = "Congress moved Tuesday on a surprise package that could reshape spending for years.\n\nAnalysts said the vote reflected months of quiet negotiation behind closed doors."
        chosen_html, chosen_text, notice, source = pick_display_body(
            feed_html,
            feed_text,
            "<p>Want to leave a tip?</p>",
            "Want to leave a tip?",
            None,
            None,
            page_attempted=True,
            page_fetched=True,
        )
        self.assertEqual(source, "feed")
        self.assertEqual(notice, CHROME_NOTICE)
        self.assertIn("Congress moved Tuesday", chosen_text or "")

    def test_html_extract_candidate_requires_two_paragraphs_and_400_chars(self):
        short = "One short paragraph that is still somewhat long but not enough letters yet."
        self.assertFalse(_html_extract_candidate_valid("<p>x</p>", short))
        long_one = "x" * 420
        self.assertFalse(_html_extract_candidate_valid(f"<p>{long_one}</p>", long_one))
        long_two = " ".join(["News lede with enough words."] * 30)
        html = f"<p>{long_two}</p><p>{long_two}</p>"
        self.assertTrue(_html_extract_candidate_valid(html, f"{long_two}\n\n{long_two}"))

    def test_single_tip_jar_paragraph_is_not_valid(self):
        tip = "Want to leave a tip? Support our journalism."
        self.assertFalse(_html_extract_candidate_valid(f"<p>{tip}</p>", tip))

    def test_dek_only_feed_is_not_full_body(self):
        dek = "These four Naruto characters prove you can surpass Kage-level strength without becoming Hokage."
        self.assertTrue(_is_dek_only(f"<p>{dek}</p>", dek))

    def test_article_needs_page_extract_for_dek_only(self):
        from app.services.extractor import article_needs_page_extract, has_full_text
        from types import SimpleNamespace

        dek = "These four Naruto characters prove you can surpass Kage-level strength without becoming Hokage."
        article = SimpleNamespace(content_html=f"<p>{dek}</p>", content_text=dek)
        self.assertTrue(article_needs_page_extract(article))
        self.assertFalse(has_full_text(article.content_html, article.content_text))

    def test_pick_display_body_prefers_page_over_dek_feed(self):
        dek = "These four Naruto characters prove you can surpass Kage-level strength without becoming Hokage."
        page_html = "<p>" + ("Full analysis paragraph with enough prose to count. " * 12) + "</p><p>" + ("Second section with more detail. " * 12) + "</p>"
        page_text = strip = " ".join(["Full analysis paragraph with enough prose to count."] * 12) + "\n\n" + " ".join(["Second section with more detail."] * 12)
        chosen_html, chosen_text, notice, source = pick_display_body(
            f"<p>{dek}</p>",
            dek,
            page_html,
            page_text,
            f"<p>{dek}</p>",
            dek,
        )
        self.assertEqual(source, "page")
        self.assertIn("Full analysis paragraph", chosen_text or "")

    def test_cbr_article_body_selector_prefers_article_body_node(self):
        from app.services.extractor import _extract_cbr_article_body

        dek = "These four Naruto characters prove you can surpass Kage-level strength without becoming Hokage."
        cbr_html = f"""
        <html><head><meta property="og:description" content="{dek}" /></head><body>
        <article class="w-article widget list layout-rich">
        <div class="article-body">
        <p>Intro paragraph with enough words to begin the ranked list article about powerful Naruto ninjas today.</p>
        <h2>10 Naruto Uzumaki</h2>
        <p>{"Naruto surpassed every Kage through hard work, Sage Mode, and the Nine-Tails partnership. " * 8}</p>
        <h2>9 Sasuke Uchiha</h2>
        <p>{"Sasuke's Sharingan and Rinnegan made him stronger than most village leaders. " * 8}</p>
        </div></article></body></html>
        """
        html, text, char_count = _extract_cbr_article_body(cbr_html, "https://www.cbr.com/example/")
        self.assertGreaterEqual(char_count, 500)
        self.assertIn("Naruto surpassed", text or "")
        self.assertNotIn(dek, (text or "")[:120])
        self.assertGreaterEqual((html or "").count("<p"), 2)

    def test_fill_article_cbr_returns_readable_notice(self):
        from app.services.extractor import CBR_NO_COLUMN_NOTICE, fill_article
        from types import SimpleNamespace

        dek = "These four Naruto characters prove you can surpass Kage-level strength without becoming Hokage."
        article = SimpleNamespace(
            url="https://www.cbr.com/naruto-ninjas-kage-level-without-kekkei-genkai/",
            content_html=f"<p>{dek}</p>",
            content_text=dek,
            feed_html=f"<p>{dek}</p>",
            feed_text=dek,
            summary=dek,
            image_url=None,
            fetched_at=None,
        )

        class FakeDb:
            def add(self, _obj) -> None:
                return None

        with unittest.mock.patch("app.services.extractor._ensure_feed_body", side_effect=lambda _db, art, refetch=False: (art.feed_html, art.feed_text)):
            with unittest.mock.patch("app.services.extractor._fetch_html_with_status", return_value=(None, 404, None)):
                updated, notice = fill_article(FakeDb(), article, force=True)  # type: ignore[arg-type]
        self.assertIn(dek, updated.content_text or "")
        self.assertEqual(notice, CBR_NO_COLUMN_NOTICE)

    def test_cbr_article_widget_class_is_not_dropped(self):
        cbr_html = """
        <html><body><article class="w-article widget list layout-rich">
        <div class="article-body">
        <p>Intro paragraph with enough words to begin the ranked list article about powerful Naruto ninjas today.</p>
        <h2>10 Naruto Uzumaki</h2>
        <p>""" + ("Naruto surpassed every Kage through hard work, Sage Mode, and the Nine-Tails partnership. " * 8) + """</p>
        <h2>9 Sasuke Uchiha</h2>
        <p>""" + ("Sasuke's Sharingan and Rinnegan made him stronger than most village leaders. " * 8) + """</p>
        </div></article></body></html>
        """
        html, text = extract_html(cbr_html, "https://www.cbr.com/example/")
        self.assertIsNotNone(text)
        assert text is not None
        self.assertIn("Naruto surpassed", text)
        self.assertIn("Sasuke", text)
        self.assertGreaterEqual((html or "").count("<h2"), 1)
        self.assertFalse(_is_dek_only(html, text))

    def test_pick_display_body_rejects_invalid_current_for_feed(self):
        para = "Congress moved Tuesday on a surprise package that could reshape spending for years to come and shift priorities."
        feed_html = f"<p>{para}</p><p>{para} Analysts said the vote reflected months of quiet negotiation behind closed doors.</p>"
        feed_text = f"{para}\n\n{para} Analysts said the vote reflected months of quiet negotiation behind closed doors."
        chosen_html, chosen_text, _notice, source = pick_display_body(
            feed_html,
            feed_text,
            "<p>Want to leave a tip?</p>",
            "Want to leave a tip?",
            "<p>Want to leave a tip?</p>",
            "Want to leave a tip?",
        )
        self.assertEqual(source, "feed")
        self.assertIn("Congress moved Tuesday", chosen_text or "")

    def test_fill_article_keeps_previous_body_on_failed_force_extract(self):
        article = SimpleNamespace(
            url="https://example.com/story",
            content_html="<p>" + ("Old body kept with enough prose to count as readable article text for tests. " * 8) + "</p><p>" + ("Second paragraph keeps the reader from going blank during re-extract. " * 8) + "</p>",
            content_text=("Old body kept with enough prose to count as readable article text for tests. " * 8).strip()
            + "\n\n"
            + ("Second paragraph keeps the reader from going blank during re-extract. " * 8).strip(),
            feed_html=None,
            feed_text=None,
            summary=None,
            image_url=None,
            fetched_at=None,
        )

        class FakeDb:
            def add(self, _obj) -> None:
                return None

        with unittest.mock.patch("app.services.extractor._ensure_feed_body", return_value=(None, None)):
            with unittest.mock.patch("app.services.extractor._fetch_html_with_status", return_value=(None, None, "Fetch failed")):
                updated, notice = fill_article(FakeDb(), article, force=True)  # type: ignore[arg-type]
        self.assertIn("Old body kept", updated.content_text or "")
        self.assertIsNone(notice)

    def test_re_extract_short_body_keeps_previous_and_does_not_shrink(self):
        """Regression: re-extract on a short-body article must keep prior text when fetch fails."""
        article = SimpleNamespace(
            url="https://example.com/short",
            content_html="<p>" + ("Readable short body kept during re-extract. " * 8) + "</p><p>" + ("Second paragraph for tests. " * 8) + "</p>",
            content_text=("Readable short body kept during re-extract. " * 8).strip()
            + "\n\n"
            + ("Second paragraph for tests. " * 8).strip(),
            feed_html=None,
            feed_text=None,
            summary=None,
            image_url=None,
            fetched_at=None,
        )

        class FakeDb:
            def add(self, _obj) -> None:
                return None

        before_len = len(article.content_text or "")
        with unittest.mock.patch("app.services.extractor._ensure_feed_body", return_value=(None, None)):
            with unittest.mock.patch("app.services.extractor._fetch_html_with_status", return_value=(None, 503, "Unavailable")):
                updated, notice = fill_article(FakeDb(), article, force=True)  # type: ignore[arg-type]
        self.assertGreaterEqual(len(updated.content_text or ""), before_len)
        self.assertIn("Readable short body kept", updated.content_text or "")
        self.assertIsNone(notice)

    def test_fill_article_keeps_feed_when_page_is_chrome(self):
        article = SimpleNamespace(
            url="https://example.com/story",
            content_html="Want to leave a tip?",
            content_text="Want to leave a tip?",
            feed_html="<p>Congress moved Tuesday on a surprise package that could reshape spending for years.</p><p>Analysts said the vote reflected months of quiet negotiation behind closed doors.</p>",
            feed_text="Congress moved Tuesday on a surprise package that could reshape spending for years.\n\nAnalysts said the vote reflected months of quiet negotiation behind closed doors.",
            summary=None,
            image_url=None,
            fetched_at=None,
        )

        class FakeDb:
            def add(self, _obj) -> None:
                return None

        page_html = "<p>Want to leave a tip?</p><p>Support Us</p>"
        with unittest.mock.patch("app.services.extractor._ensure_feed_body", side_effect=lambda _db, art, refetch=False: (art.feed_html, art.feed_text)):
            with unittest.mock.patch("app.services.extractor._fetch_html_with_status", return_value=("<html></html>", 200, None)):
                with unittest.mock.patch(
                    "app.services.extractor._extract_from_html",
                    return_value=(page_html, "Want to leave a tip?\nSupport Us"),
                ):
                    updated, notice = fill_article(FakeDb(), article, force=True)  # type: ignore[arg-type]
        self.assertIn("Congress moved Tuesday", updated.content_text or "")
        self.assertEqual(notice, CHROME_NOTICE)


if __name__ == "__main__":
    unittest.main()
