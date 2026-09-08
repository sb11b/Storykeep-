from __future__ import annotations

import unittest
from datetime import datetime, timezone
from uuid import uuid4

from app.schemas import AnnotationOut
from app.services.notes_feed import paginate_notes


def _note(kind: str, when: datetime) -> AnnotationOut:
    return AnnotationOut(
        id=uuid4(),
        article_id=uuid4(),
        body=kind,
        quote="q" if kind != "note" else None,
        kind=kind,
        created_at=when,
        updated_at=when,
        article_title="Article",
    )


class NotesFeedTests(unittest.TestCase):
    def test_paginate_keeps_highlights_and_additions(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        items = [_note("note", now), _note("highlight", now), _note("addition", now)]
        page, total = paginate_notes(items, limit=40, offset=0)
        self.assertEqual(total, 3)
        self.assertEqual(len(page), 3)
        self.assertEqual({item.kind for item in page}, {"note", "highlight", "addition"})

    def test_paginate_second_page(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        items = [_note("note", now) for _ in range(5)]
        page, total = paginate_notes(items, limit=2, offset=2)
        self.assertEqual(total, 5)
        self.assertEqual(len(page), 2)


if __name__ == "__main__":
    unittest.main()
