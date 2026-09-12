from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.services.tts import (
    article_script,
    body_sections,
    is_composed_note,
    note_source_markdown,
    script_digest,
    section_start_words,
    speech_plain,
    spoken_title,
    word_count,
)


class SpeechPlainTests(unittest.TestCase):
    def test_skips_highlight_markers_and_images(self):
        html = '<p>The <mark>derivative</mark> is the slope.</p><img alt="plot" src="/api/v1/media/11111111-1111-1111-1111-111111111111" />'
        self.assertEqual(speech_plain(html), "The derivative is the slope.")
        md = "The ==derivative== is the slope.\n![plot](/api/v1/media/11111111-1111-1111-1111-111111111111)"
        self.assertEqual(speech_plain(md), "The derivative is the slope.")
        self.assertNotIn("==", speech_plain(md))
        self.assertNotIn("plot", speech_plain(md))
        self.assertEqual(
            speech_plain("==Line one\n\n• bullet== leftover"),
            "Line one • bullet leftover",
        )

    def test_title_word_count_matches_spoken_title(self):
        self.assertEqual(word_count(spoken_title("Note highlights demo")), 3)

    def test_digest_changes_with_body_and_sections_split(self):
        self.assertNotEqual(script_digest("hello", "eve"), script_digest("hello world", "eve"))
        self.assertEqual(script_digest("same", "eve"), script_digest("same", "eve"))

        class Fake:
            title = "_book_demo"
            content_text = "# Limits\nA limit is...\n\n# Derivatives\nSlope of the tangent."
            content_html = None
            summary = None
            guid = "rss:1"
            overlay_additions = []

        sections = body_sections(Fake())
        self.assertGreaterEqual(len(sections), 2)
        self.assertEqual(sections[0]["title"], "Limits")

    def test_composed_note_script_uses_markdown_not_rss_html(self):
        note = SimpleNamespace(
            title="Lecture notes",
            guid="storykeep-note:abc",
            content_text="The ==slope== of y.\n![plot](/api/v1/media/11111111-1111-1111-1111-111111111111)",
            content_html="<p>stale html that must not win</p>",
            summary="",
            overlay_additions=[],
        )
        self.assertTrue(is_composed_note(note))
        script = article_script(note)
        self.assertIn("slope of y", script)
        self.assertNotIn("stale html", script)
        self.assertNotIn("==", script)
        self.assertNotIn("plot", script)

    def test_overlay_markdown_fills_empty_composed_body(self):
        note = SimpleNamespace(
            title="Addition",
            guid="storykeep-note:xyz",
            content_text="",
            content_html="",
            summary="",
            overlay_additions=[SimpleNamespace(markdown="Remember the chain rule.")],
        )
        self.assertEqual(note_source_markdown(note), "Remember the chain rule.")
        self.assertIn("chain rule", article_script(note))

    def test_article_script_prefers_clean_text_over_polluted_html(self):
        article = SimpleNamespace(
            title="Policy story",
            guid="https://example.com/1",
            content_text="Congress moved Tuesday on a surprise package.",
            content_html='<style>.widget{box-sizing:border-box;}</style><p>Congress moved Tuesday on a surprise package.</p>',
            summary="",
            overlay_additions=[],
        )
        script = article_script(article)
        self.assertIn("Congress moved Tuesday", script)
        self.assertNotIn("box-sizing", script)
        self.assertNotIn("widget", script)

    def test_section_start_words_skip_title_then_accumulate(self):
        note = SimpleNamespace(
            title="Course notes",
            guid="storykeep-note:abc",
            content_text="# Intro\nFirst paragraph.\n\n# Chapter two\nSecond part continues.",
            content_html="",
            summary="",
            overlay_additions=[],
        )
        starts = section_start_words(note)
        self.assertEqual(starts["0"], word_count(spoken_title(note.title)))
        intro_words = word_count(speech_plain("# Intro\nFirst paragraph."))
        self.assertEqual(starts["1"], starts["0"] + intro_words)

    def test_include_notes_appends_overlay_notes_without_changing_article_body(self):
        article = SimpleNamespace(
            title="RSS story",
            guid="https://example.com/1",
            content_text="Original article body stays.",
            content_html="<p>Original article body stays.</p>",
            summary="",
            overlay_additions=[],
        )
        without = article_script(article)
        with_notes = article_script(
            article,
            include_notes=True,
            extra_notes=[("My note", "I typed ==this== aside.")],
        )
        self.assertIn("Original article body stays", without)
        self.assertNotIn("I typed", without)
        self.assertIn("Original article body stays", with_notes)
        self.assertIn("I typed this aside", with_notes)
        self.assertNotIn("==", with_notes)


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
