import unittest
import unittest.mock
from types import SimpleNamespace
from uuid import uuid4

from app.services.corrections import correction_for_article, upsert_correction


class FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeDb:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.deleted = []
        self.added = []

    def scalars(self, _query):
        return FakeScalars(self.rows)

    def add(self, row):
        self.added.append(row)
        self.rows.append(row)

    def delete(self, row):
        self.deleted.append(row)
        if row in self.rows:
            self.rows.remove(row)

    def flush(self):
        return None

    def commit(self):
        return None

    def refresh(self, _row):
        return None


class CorrectionServiceTests(unittest.TestCase):
    def test_upsert_updates_existing_correction(self):
        article_id = uuid4()
        user_id = uuid4()
        existing = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            article_id=article_id,
            markdown="first",
            created_at=None,
        )
        db = FakeDb([existing])
        user = SimpleNamespace(id=user_id)
        article = SimpleNamespace(id=article_id)

        with unittest.mock.patch("app.services.corrections.changelog.record"):
            row = upsert_correction(db, user, article, "second pass")

        self.assertIs(row, existing)
        self.assertEqual(existing.markdown, "second pass")
        self.assertEqual(len(db.added), 0)

    def test_correction_save_twice_one_row_latest_text(self):
        article_id = uuid4()
        user_id = uuid4()
        existing = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            article_id=article_id,
            markdown="first",
            created_at=None,
        )
        db = FakeDb([existing])
        user = SimpleNamespace(id=user_id)
        article = SimpleNamespace(id=article_id)

        with unittest.mock.patch("app.services.corrections.changelog.record"):
            upsert_correction(db, user, article, "second pass")
            row = upsert_correction(db, user, article, "third pass")

        self.assertIs(row, existing)
        self.assertEqual(existing.markdown, "third pass")
        self.assertEqual(len(db.rows), 1)
        self.assertEqual(len(db.added), 0)


if __name__ == "__main__":
    unittest.main()
