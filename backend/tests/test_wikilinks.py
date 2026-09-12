from __future__ import annotations

import unittest
import uuid

from app.database import SessionLocal
from app.models import Article, Feed, User
from app.services.wikilinks import parse_wikilink_targets, resolve_note_by_title, resolve_note_titles


class WikilinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        self.user = User(
            id=uuid.uuid4(),
            email=f"wikilink-{uuid.uuid4()}@example.com",
            password_hash="x",
        )
        self.db.add(self.user)
        self.db.flush()
        self.feed = Feed(user_id=self.user.id, url=f"https://example.com/{uuid.uuid4()}", title="Feed")
        self.db.add(self.feed)
        self.db.flush()

    def tearDown(self) -> None:
        self.db.rollback()
        self.db.close()

    def _article(self, title: str, *, destination: str | None = None) -> Article:
        article = Article(
            feed_id=self.feed.id,
            guid=f"storykeep-note:{uuid.uuid4()}",
            url=f"storykeep://note/{uuid.uuid4()}",
            title=title,
            destination=destination,
        )
        self.db.add(article)
        self.db.flush()
        return article

    def test_parse_wikilink_targets(self):
        text = "See [[DAT 325 Project One|project]] and [[Other]]"
        self.assertEqual(parse_wikilink_targets(text), ["DAT 325 Project One", "Other"])

    def test_resolve_exact_then_case_insensitive_then_starts_with(self):
        exact = self._article("DAT 325 Project One", destination="schoolwork")
        self._article("dat 325 project one extra", destination="notes")
        self._article("DAT 325", destination="notes")

        hit = resolve_note_by_title(self.db, self.user, "DAT 325 Project One", shelf="schoolwork")
        self.assertEqual(hit.id, exact.id)

        ci = resolve_note_by_title(self.db, self.user, "dat 325 project one")
        self.assertEqual(ci.title, "DAT 325 Project One")

        sw = resolve_note_by_title(self.db, self.user, "DAT 325")
        self.assertTrue(sw.title.startswith("DAT 325"))

    def test_prefer_same_shelf_when_multiple_exact(self):
        notes = self._article("Shared Title", destination="notes")
        school = self._article("Shared Title", destination="schoolwork")
        del notes, school
        hit = resolve_note_by_title(self.db, self.user, "Shared Title", shelf="schoolwork")
        self.assertEqual(hit.destination, "schoolwork")

    def test_resolve_batch(self):
        target = self._article("Batch Note")
        results = resolve_note_titles(self.db, self.user, ["Batch Note", "Missing"])
        self.assertEqual(results["Batch Note"].id, target.id)
        self.assertIsNone(results["Missing"])


if __name__ == "__main__":
    unittest.main()
