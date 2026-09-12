from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.folders import create_folder, delete_folder, normalize_folder_shelf, rename_folder


class FolderServiceTests(unittest.TestCase):
    def test_normalize_folder_shelf(self):
        self.assertEqual(normalize_folder_shelf("Schoolwork"), "schoolwork")
        with self.assertRaises(ValueError):
            normalize_folder_shelf("inbox")

    def test_create_folder_rejects_duplicate_name(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4())
        db = MagicMock()
        db.scalar.return_value = SimpleNamespace(id=uuid.uuid4())
        with self.assertRaises(ValueError):
            create_folder(db, user, "schoolwork", "DAT-325")

    def test_delete_folder_clears_article_links(self):
        user = SimpleNamespace(id=uuid.uuid4())
        folder_id = uuid.uuid4()
        folder = SimpleNamespace(id=folder_id, user_id=user.id, shelf="schoolwork", name="DAT-325")
        article = SimpleNamespace(id=uuid.uuid4(), folder_id=folder_id)
        db = MagicMock()
        db.scalar.return_value = folder
        db.scalars.return_value.all.return_value = [article]

        delete_folder(db, user, folder_id)

        self.assertIsNone(article.folder_id)
        db.delete.assert_called_with(folder)
        db.commit.assert_called_once()

    def test_rename_folder_updates_name(self):
        user = SimpleNamespace(id=uuid.uuid4())
        folder_id = uuid.uuid4()
        folder = SimpleNamespace(id=folder_id, user_id=user.id, shelf="schoolwork", name="Old")
        db = MagicMock()
        db.scalar.side_effect = [folder, None]

        row = rename_folder(db, user, folder_id, "DAT-325")

        self.assertEqual(row.name, "DAT-325")
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
