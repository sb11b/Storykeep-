from __future__ import annotations

import unittest
import zipfile
from io import BytesIO

from app.services.vault_paths import (
    import_tags_for_path,
    is_markdown,
    normalize_zip_name,
    overlay_relpath,
    parse_hashtags,
    parse_wikilinks,
    source_kind_for_path,
    vault_relative_from_zip_names,
)


class VaultPathTests(unittest.TestCase):
    def test_skips_obsidian_and_empty(self):
        self.assertIsNone(normalize_zip_name(".obsidian/app.json"))
        self.assertIsNone(normalize_zip_name("Steve's Surface Vault/.obsidian/workspace.json"))
        self.assertIsNone(normalize_zip_name("\\"))
        self.assertIsNone(normalize_zip_name("/"))
        self.assertIsNone(normalize_zip_name("folder/"))

    def test_strips_root_and_backslashes(self):
        self.assertEqual(
            normalize_zip_name("Steve's Surface Vault\\Daily Notes\\2024-01-01.md"),
            "Daily Notes/2024-01-01.md",
        )
        self.assertEqual(normalize_zip_name("Clippings/(&).md"), "Clippings/(&).md")
        self.assertEqual(normalize_zip_name("(.md"), "(.md")
        self.assertTrue(is_markdown("notes/en–dash.md"))

    def test_kind_and_tags(self):
        self.assertEqual(source_kind_for_path("_book_calculus.md"), "textbook")
        self.assertIn("book", import_tags_for_path("Books/_book_stats.md"))
        self.assertIn("course", import_tags_for_path("_DAT-200 intro.md"))
        self.assertIn("clipping", import_tags_for_path("Clippings/foo.md"))
        self.assertIn("daily", import_tags_for_path("Daily Notes/2024-01-01.md"))

    def test_wikilinks_and_tags(self):
        text = "See [[Other Note|label]] and #fusion in class."
        self.assertEqual(parse_wikilinks(text), ["Other Note"])
        self.assertEqual(parse_hashtags(text), ["fusion"])

    def test_windows_pack_paths(self):
        path = overlay_relpath("highlight", r"Daily Notes\bad:name.md", "id")
        self.assertTrue(path.startswith("StoryKeep/Highlights/"))
        self.assertNotIn(":", path)
        self.assertNotIn("\\", path)
        self.assertTrue(path.endswith(".md"))
        dashed = overlay_relpath("correction", "Books/Calc – limits.md", "id")
        self.assertTrue(dashed.startswith("StoryKeep/Corrections/"))
        self.assertIn("Calc", dashed)
        odd = overlay_relpath("addition", None, "(.md")
        self.assertTrue(odd.startswith("StoryKeep/Additions/"))
        self.assertTrue(odd.endswith(".md"))
        self.assertNotIn(":", odd)

    def test_zip_listing(self):
        buf = BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("Steve's Surface Vault/.obsidian/app.json", "{}")
            zf.writestr("Steve's Surface Vault/(.md", "# odd")
            zf.writestr("Steve's Surface Vault\\_book_demo.md", "book")
            zf.writestr("\\\\", "nope")
        names = zipfile.ZipFile(buf).namelist()
        cleaned = [normalize_zip_name(name) for name in names]
        self.assertIn("(.md", cleaned)
        self.assertIn("_book_demo.md", cleaned)
        self.assertTrue(any(item is None for item in cleaned))
        self.assertEqual(vault_relative_from_zip_names(["Steve's Surface Vault/a.md"]), ["a.md"])


if __name__ == "__main__":
    unittest.main()
