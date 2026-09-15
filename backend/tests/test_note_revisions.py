from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.database import SessionLocal, get_db
from app.deps import get_current_user
from app.models import Article, Feed, NoteRevision, User
from app.routers import overlay as overlay_router
from app.services.note_revisions import (
    NoteShrinkBlocked,
    is_severe_shrink,
    list_revisions,
    prune_revisions,
    snapshot_before_save,
    shrink_confirm_message,
)
from app.services.vault_import import create_composed_note, update_composed_note


class NoteRevisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        self.user = User(
            id=uuid.uuid4(),
            email=f"revisions-{uuid.uuid4()}@example.com",
            password_hash="x",
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.rollback()
        self.db.close()

    def test_severe_shrink_threshold(self):
        self.assertTrue(is_severe_shrink(15000, 239))
        self.assertFalse(is_severe_shrink(100, 50))
        self.assertFalse(is_severe_shrink(30, 1))
        self.assertEqual(
            shrink_confirm_message(15000, 239),
            "This save is much shorter (239 vs 15000). Save anyway?",
        )

    def test_long_save_then_short_blocked_then_confirm_and_undo(self):
        long_body = ("alpha " * 2500).strip()
        short_body = "oops, almost empty"
        self.assertGreater(len(long_body), 10000)
        self.assertLess(len(short_body) / len(long_body), 0.2)

        article = create_composed_note(self.db, self.user, "Long note", long_body, destination="notes")
        article = update_composed_note(self.db, self.user, article, "Long note", long_body + "\n\nMore.")
        self.assertEqual(len(list_revisions(self.db, self.user, article)), 1)
        stored_long = article.content_text
        self.assertIn("More.", stored_long or "")

        with self.assertRaises(NoteShrinkBlocked) as raised:
            update_composed_note(self.db, self.user, article, "Long note", short_body)
        self.assertEqual(raised.exception.current_chars, len(stored_long or ""))
        self.assertEqual(raised.exception.incoming_chars, len(short_body))
        self.db.refresh(article)
        self.assertEqual(article.content_text, stored_long)
        self.assertEqual(len(list_revisions(self.db, self.user, article)), 1)

        update_composed_note(
            self.db, self.user, article, "Long note", short_body, confirm_short=True
        )
        self.assertEqual(article.content_text, short_body)
        self.assertEqual(len(list_revisions(self.db, self.user, article)), 2)

        previous = list_revisions(self.db, self.user, article)[0]
        self.assertEqual(previous.markdown, stored_long)
        update_composed_note(
            self.db,
            self.user,
            article,
            "Long note",
            previous.markdown,
            confirm_short=True,
            snapshot=False,
        )
        self.assertEqual(article.content_text, stored_long)

    def test_prune_keeps_twenty(self):
        article = create_composed_note(self.db, self.user, "Keep twenty", "seed body for revisions", destination="notes")
        now = datetime.now(timezone.utc)
        for i in range(25):
            self.db.add(
                NoteRevision(
                    user_id=self.user.id,
                    article_id=article.id,
                    markdown=f"rev-{i}",
                    char_count=5,
                    created_at=now - timedelta(minutes=i),
                )
            )
        self.db.flush()
        prune_revisions(self.db, self.user, article.id)
        kept = list_revisions(self.db, self.user, article)
        self.assertEqual(len(kept), 20)
        self.assertEqual(kept[0].markdown, "rev-0")

    def test_vault_original_is_rejected(self):
        feed = Feed(user_id=self.user.id, url=f"https://example.com/{uuid.uuid4()}", title="Vault")
        self.db.add(feed)
        self.db.flush()
        article = Article(
            feed_id=feed.id,
            guid=f"obsidian:{uuid.uuid4()}",
            url="obsidian://note",
            title="Vault original",
            content_text="do not overwrite",
            source_kind="obsidian",
        )
        self.db.add(article)
        self.db.flush()
        with self.assertRaises(HTTPException) as raised:
            snapshot_before_save(self.db, self.user, article, "tiny")
        self.assertEqual(raised.exception.status_code, 400)

    def test_patch_route_returns_409_before_overwrite(self):
        long_body = ("beta " * 2500).strip()
        article = create_composed_note(self.db, self.user, "HTTP shrink", long_body, destination="notes")
        update_composed_note(self.db, self.user, article, "HTTP shrink", long_body + " extra")

        def fake_db():
            yield self.db

        app = FastAPI()
        app.include_router(overlay_router.router, prefix="/api/v1")
        app.dependency_overrides[get_db] = fake_db
        app.dependency_overrides[get_current_user] = lambda: self.user
        client = TestClient(app)
        response = client.patch(
            f"/api/v1/articles/{article.id}/storykeep-note",
            json={"title": "HTTP shrink", "markdown": "tiny accident"},
        )
        self.assertEqual(response.status_code, 409)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "note_shrink")
        self.assertIn("much shorter", detail["message"])
        self.db.refresh(article)
        self.assertIn("extra", article.content_text or "")


if __name__ == "__main__":
    unittest.main()
