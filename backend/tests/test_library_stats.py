from __future__ import annotations

import unittest
import uuid
from unittest.mock import MagicMock, patch

from app.models import User
from app.routers.library import stats


class LibraryStatsTests(unittest.TestCase):
    @patch("app.routers.library.shelf_count")
    def test_schoolwork_badge_equals_shelf_item_count(self, mock_shelf_count: MagicMock) -> None:
        user = User(id=uuid.uuid4(), email="test@example.com", password_hash="x")
        db = MagicMock()
        db.scalar.return_value = 0

        def count_side_effect(_db, _user, shelf: str) -> int:
            return {"schoolwork": 7, "notes": 2, "vault": 1, "additions": 3, "books": 4}[shelf]

        mock_shelf_count.side_effect = count_side_effect

        result = stats(db=db, user=user)

        mock_shelf_count.assert_any_call(db, user, "schoolwork")
        self.assertEqual(result.schoolwork_count, 7)


if __name__ == "__main__":
    unittest.main()
