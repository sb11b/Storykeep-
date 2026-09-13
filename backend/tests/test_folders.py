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

    def test_create_folder_returns_existing_on_this_shelf(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4())
        existing = SimpleNamespace(id=uuid.uuid4(), shelf="schoolwork", name="DAT-325")
        db = MagicMock()
        db.scalar.return_value = existing
        row = create_folder(db, user, "schoolwork", "DAT-325")
        self.assertIs(row, existing)
        db.add.assert_not_called()

    def test_resolve_folder_id_stays_on_requested_shelf(self) -> None:
        from app.services.folders import resolve_folder_id

        user = SimpleNamespace(
            id=uuid.uuid4(),
            preferences={"custom_note_shelves": [{"id": "junior", "name": "Junior"}, {"id": "editions", "name": "Editions"}]},
        )
        other = SimpleNamespace(id=uuid.uuid4(), user_id=user.id, shelf="editions", name="transfer block")
        local = SimpleNamespace(id=uuid.uuid4(), user_id=user.id, shelf="junior", name="transfer block")
        db = MagicMock()
        db.scalar.side_effect = [other, local]
        resolved = resolve_folder_id(db, user, "junior", other.id)
        self.assertEqual(resolved, local.id)
        db.add.assert_not_called()

    def test_resolve_folder_id_creates_on_requested_shelf_when_missing(self) -> None:
        from app.services import folders as folders_mod

        user = SimpleNamespace(
            id=uuid.uuid4(),
            preferences={"custom_note_shelves": [{"id": "junior", "name": "Junior"}, {"id": "editions", "name": "Editions"}]},
        )
        other = SimpleNamespace(id=uuid.uuid4(), user_id=user.id, shelf="editions", name="transfer block")
        created = SimpleNamespace(id=uuid.uuid4(), user_id=user.id, shelf="junior", name="transfer block")
        db = MagicMock()
        db.scalar.side_effect = [other]
        with patch.object(folders_mod, "ensure_folder_on_shelf", return_value=created) as ensure:
            resolved = folders_mod.resolve_folder_id(db, user, "junior", other.id)
        self.assertEqual(resolved, created.id)
        ensure.assert_called_once()
        self.assertEqual(ensure.call_args.args[2], "junior")
        self.assertEqual(ensure.call_args.args[3], "transfer block")

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
