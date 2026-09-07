from __future__ import annotations

import unittest

from app.services.vault_paths import classify_zip_entry, overlay_relpath


class OverlayPackTests(unittest.TestCase):
    def test_pack_paths_are_windows_safe_and_under_storykeep(self):
        highlight = overlay_relpath("highlight", r"Daily Notes\bad:name.md", "id")
        correction = overlay_relpath("correction", "Clippings/(&).md", "id")
        addition = overlay_relpath("addition", None, "My new note?")
        self.assertTrue(highlight.startswith("StoryKeep/Highlights/"))
        self.assertTrue(correction.startswith("StoryKeep/Corrections/"))
        self.assertTrue(addition.startswith("StoryKeep/Additions/"))
        for path in (highlight, correction, addition):
            self.assertNotIn(":", path)
            self.assertNotIn("?", path)
            self.assertNotIn("Steve's Surface Vault", path)
            self.assertTrue(path.endswith(".md"))

    def test_classify_skips_obsidian_and_images(self):
        self.assertEqual(classify_zip_entry("Steve's Surface Vault/.obsidian/app.json")[0], "skip")
        self.assertEqual(classify_zip_entry("\\\\")[0], "skip")
        self.assertEqual(classify_zip_entry("Clippings/photo.png"), ("image", "Clippings/photo.png"))
        self.assertEqual(classify_zip_entry("Steve's Surface Vault/(.md"), ("markdown", "(.md"))
        self.assertEqual(classify_zip_entry("Steve's Surface Vault\\_book_demo.md"), ("markdown", "_book_demo.md"))


if __name__ == "__main__":
    unittest.main()
