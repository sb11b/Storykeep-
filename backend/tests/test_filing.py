from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.destination import shelf_where
from app.services.filing import set_article_filing


class FilingTests(unittest.TestCase):
    def test_shelf_where_includes_explicit_destination(self):
        self.assertIsNotNone(shelf_where("schoolwork"))

    def test_set_article_filing_rss_sets_destination(self):
        user = SimpleNamespace(id=uuid.uuid4())
        article = SimpleNamespace(
            id=uuid.uuid4(),
            guid="https://example.com/story",
            source_kind="rss",
            destination=None,
            folder_id=None,
            updated_at=None,
        )
        db = MagicMock()
        with patch("app.services.filing.changelog.record"):
            row = set_article_filing(db, user, article, "schoolwork", folder_id=None, commit=False)
        self.assertEqual(row.destination, "schoolwork")
        self.assertIsNone(row.folder_id)
        db.flush.assert_called_once()

    def test_create_composed_note_writes_junior_folder_and_marks_read(self):
        from app.services.vault_import import create_composed_note

        user = SimpleNamespace(
            id=uuid.uuid4(),
            preferences={"custom_note_shelves": [{"id": "junior", "name": "Junior"}]},
        )
        folder_id = uuid.uuid4()
        db = MagicMock()
        db.scalars.return_value.first.return_value = None
        with (
            patch("app.services.vault_import.normalize_destination", return_value="junior"),
            patch("app.services.folders.resolve_folder_id", return_value=folder_id),
            patch("app.services.vault_import.vault_feed", return_value=SimpleNamespace(id=uuid.uuid4())),
            patch("app.services.vault_import.changelog.record"),
        ):
            article = create_composed_note(
                db,
                user,
                "Junior memory",
                "Standing context.",
                destination="junior",
                folder_id=folder_id,
            )
        self.assertEqual(article.destination, "junior")
        self.assertEqual(article.folder_id, folder_id)
        self.assertTrue(article.is_read)
        self.assertTrue(article.is_saved)

    def test_create_composed_note_patches_existing_title_on_same_folder(self):
        from app.services.vault_import import create_composed_note

        user = SimpleNamespace(
            id=uuid.uuid4(),
            preferences={"custom_note_shelves": [{"id": "junior", "name": "Junior"}]},
        )
        folder_id = uuid.uuid4()
        existing = SimpleNamespace(
            id=uuid.uuid4(),
            guid="storykeep-note:keep",
            destination="junior",
            folder_id=folder_id,
            is_correction=False,
            source_kind="obsidian",
            overlay_additions=[],
        )
        db = MagicMock()
        db.scalars.return_value.first.return_value = existing
        db.scalar.return_value = None
        with (
            patch("app.services.vault_import.normalize_destination", return_value="junior"),
            patch("app.services.folders.resolve_folder_id", return_value=folder_id),
            patch("app.services.vault_import.markdown_to_html", return_value="<p>x</p>"),
            patch("app.services.note_revisions.snapshot_before_save"),
            patch("app.services.vault_import.changelog.record"),
        ):
            article = create_composed_note(
                db,
                user,
                "Junior memory",
                "Updated body for the same note.",
                destination="junior",
                folder_id=folder_id,
            )
        self.assertIs(article, existing)
        self.assertEqual(existing.content_text, "Updated body for the same note.")
        self.assertEqual(existing.destination, "junior")
        self.assertEqual(existing.folder_id, folder_id)

    def test_set_article_filing_rejects_vault_import(self):
        user = SimpleNamespace(id=uuid.uuid4())
        article = SimpleNamespace(
            id=uuid.uuid4(),
            guid="obsidian:Schoolwork/note.md",
            source_kind="obsidian",
            destination=None,
            folder_id=None,
        )
        db = MagicMock()
        with self.assertRaises(ValueError):
            set_article_filing(db, user, article, "schoolwork", folder_id=None)


if __name__ == "__main__":
    unittest.main()
