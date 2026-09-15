from __future__ import annotations

import unittest

from app.services.destination import (
    DEFAULT_DESTINATION,
    apply_destination,
    normalize_destination,
    source_kind_for_destination,
    shelf_where,
)
from app.services.vault_paths import overlay_relpath


class DestinationTests(unittest.TestCase):
    def test_normalize_default_and_reject(self):
        self.assertEqual(normalize_destination(None), DEFAULT_DESTINATION)
        self.assertEqual(normalize_destination("Schoolwork"), "schoolwork")
        with self.assertRaises(ValueError):
            normalize_destination("obsidian")

    def test_shelf_filters_exist(self):
        for shelf in ("vault", "additions", "books", "notes", "schoolwork"):
            self.assertIsNotNone(shelf_where(shelf))

    def test_vault_import_has_changelog(self):
        from app.services import vault_import

        self.assertTrue(hasattr(vault_import, "changelog"))

    def test_apply_destination_sets_books_kind(self):
        article = type("Article", (), {"destination": None, "source_kind": "obsidian", "is_correction": False})()
        apply_destination(article, "books", True)
        self.assertEqual(article.destination, "books")
        self.assertEqual(article.source_kind, "textbook")
        self.assertTrue(article.is_correction)
        self.assertEqual(source_kind_for_destination("schoolwork"), "obsidian")

    def test_correction_pack_path(self):
        path = overlay_relpath("correction", None, "calc-notes")
        self.assertTrue(path.startswith("StoryKeep/Corrections/"))
        add = overlay_relpath("addition", None, "calc-notes")
        self.assertTrue(add.startswith("StoryKeep/Additions/"))

    def test_effective_destination_for_filed_rss(self):
        from app.services.destination import effective_destination

        article = type(
            "Article",
            (),
            {"guid": "https://example.com/story", "source_kind": "rss", "destination": "schoolwork"},
        )()
        self.assertEqual(effective_destination(article), "schoolwork")

    def test_effective_destination_keeps_custom_junior_shelf(self):
        from app.services.destination import effective_destination

        article = type(
            "Article",
            (),
            {"guid": "storykeep-note:abc", "source_kind": "obsidian", "destination": "junior"},
        )()
        self.assertEqual(effective_destination(article), "junior")


if __name__ == "__main__":
    unittest.main()
