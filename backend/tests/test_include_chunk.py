from __future__ import annotations

import unittest

from app.services.include_chunk import (
    INCLUDE_TURN_CHAR_CAP,
    format_include_chip,
    parse_sections,
    resolve_include_slice,
)


DAT = """# DAT-200 notes

Lead-in paragraph.

## Completeness

Completeness means every fact that belongs on a row is stored on that row.
""" + ("Keep the grade with the enrollment. " * 80) + """

## Third normal form

Non-key attributes must depend on the key, the whole key, and nothing but the key.
""" + ("Normalize repeating groups. " * 40)


class IncludeChunkTests(unittest.TestCase):
    def test_chip_uses_section_sign_and_char_count(self):
        self.assertEqual(format_include_chip("Completeness", 1842), "§ Completeness (1,842 chars)")

    def test_parses_markdown_h2_sections(self):
        titles = [item[0] for item in parse_sections(DAT)]
        self.assertIn("Completeness", titles)
        self.assertIn("Third normal form", titles)

    def test_heading_slice_is_not_the_whole_book(self):
        slice = resolve_include_slice(DAT, mode="heading", heading="Completeness", title="DAT-200 notes")
        self.assertEqual(slice.label, "Completeness")
        self.assertIn("every fact that belongs", slice.text)
        self.assertNotIn("nothing but the key", slice.text)
        self.assertTrue(slice.has_more)
        self.assertEqual(slice.next_heading, "Third normal form")
        self.assertEqual(slice.chip, format_include_chip("Completeness", slice.chars))
        self.assertLess(slice.chars, len(DAT))

    def test_selection_slice(self):
        quote = "Completeness means every fact that belongs on a row is stored on that row."
        slice = resolve_include_slice(DAT, mode="selection", selection=quote)
        self.assertEqual(slice.label, "Selection")
        self.assertEqual(slice.text, quote)
        self.assertTrue(slice.has_more)

    def test_first_chunk_caps_and_offers_next(self):
        huge = "# Book\n\n" + ("chapter text " * 5000)
        slice = resolve_include_slice(huge, mode="chunk", title="Book")
        self.assertLessEqual(slice.chars, INCLUDE_TURN_CHAR_CAP)
        self.assertTrue(slice.has_more)
        self.assertIsNotNone(slice.next_offset)
        nxt = resolve_include_slice(huge, mode="chunk", offset=slice.next_offset, title="Book")
        self.assertTrue(nxt.text)
        self.assertNotEqual(nxt.text[:40], slice.text[:40])

    def test_short_article_sends_in_full(self):
        body = "## Intro\n\nA short DAT note."
        slice = resolve_include_slice(body, mode="auto", title="Intro note")
        self.assertFalse(slice.has_more)
        self.assertIn("short DAT note", slice.text)


if __name__ == "__main__":
    unittest.main()
