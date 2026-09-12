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
