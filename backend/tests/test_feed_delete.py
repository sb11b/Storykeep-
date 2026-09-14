from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.database import get_db
from app.deps import get_current_user
from app.routers import feeds as feeds_router
from app.services.feed_delete import SAVED_CONFLICT, owned_feed, remove_feed


class FeedDeleteTests(unittest.TestCase):
    def test_other_owner_is_404(self):
        user = SimpleNamespace(id=uuid4())
        other = SimpleNamespace(id=uuid4(), user_id=uuid4())
        db = MagicMock()
        db.get.return_value = other
        with self.assertRaises(HTTPException) as raised:
            owned_feed(db, user, other.id)
        self.assertEqual(raised.exception.status_code, 404)

    def test_saved_articles_conflict_without_force(self):
        user = SimpleNamespace(id=uuid4())
        feed = SimpleNamespace(id=uuid4(), user_id=user.id, url="https://example.com/rss")
        db = MagicMock()
        db.get.return_value = feed
        db.scalar.return_value = 1
        with self.assertRaises(HTTPException) as raised:
            remove_feed(db, user, feed.id, force=False)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail, SAVED_CONFLICT)
        db.commit.assert_not_called()

    def test_force_keeps_saved_and_deletes_feed(self):
        user = SimpleNamespace(id=uuid4())
        feed = SimpleNamespace(id=uuid4(), user_id=user.id, url="https://example.com/rss")
        db = MagicMock()
        db.get.return_value = feed
        db.scalar.return_value = 1
        with patch("app.services.feed_delete.changelog.record"):
            result = remove_feed(db, user, feed.id, force=True)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(db.execute.call_count, 3)
        db.commit.assert_called_once()

    def test_post_and_delete_routes(self):
        user = SimpleNamespace(id=uuid4(), email="reader@example.com", is_demo_locked=False)
        feed_id = uuid4()
        db = MagicMock()

        def fake_db():
            yield db

        app = FastAPI()
        app.include_router(feeds_router.router, prefix="/api/v1")
        app.dependency_overrides[get_db] = fake_db
        app.dependency_overrides[get_current_user] = lambda: user
        client = TestClient(app)
        with patch("app.routers.feeds.feed_delete.remove_feed", return_value={"ok": True}) as remove:
            deleted = client.delete(f"/api/v1/feeds/{feed_id}")
            posted = client.post(f"/api/v1/feeds/{feed_id}", json={"force": True})
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(remove.call_count, 2)
        self.assertTrue(remove.call_args.kwargs["force"])

    def test_post_409_when_saved(self):
        user = SimpleNamespace(id=uuid4(), email="reader@example.com", is_demo_locked=False)
        db = MagicMock()

        def fake_db():
            yield db

        app = FastAPI()
        app.include_router(feeds_router.router, prefix="/api/v1")
        app.dependency_overrides[get_db] = fake_db
        app.dependency_overrides[get_current_user] = lambda: user
        client = TestClient(app)
        with patch(
            "app.routers.feeds.feed_delete.remove_feed",
            side_effect=HTTPException(status_code=409, detail=SAVED_CONFLICT),
        ):
            response = client.post(f"/api/v1/feeds/{uuid4()}", json={"force": False})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], SAVED_CONFLICT)


if __name__ == "__main__":
    unittest.main()
