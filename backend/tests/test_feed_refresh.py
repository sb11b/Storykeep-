from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import get_db
from app.deps import get_current_user
from app.main import http_exception_with_message, request_validation_handler
from app.routers import feeds as feeds_router
from fastapi.exceptions import RequestValidationError


def _app(user=None):
    app = FastAPI()
    app.add_exception_handler(StarletteHTTPException, http_exception_with_message)
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.include_router(feeds_router.router, prefix="/api/v1")
    owner = user or SimpleNamespace(id=uuid4(), email="reader@example.com", is_demo_locked=False)
    db = MagicMock()

    def fake_db():
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_user] = lambda: owner
    return app, db, owner


class FeedRefreshRouteTests(unittest.TestCase):
    def test_collection_refresh_is_not_a_uuid_slot(self):
        app, _db, _owner = _app()
        with patch("app.routers.feeds.rss.refresh_user_feeds", return_value=3) as refresh_all:
            client = TestClient(app)
            response = client.post("/api/v1/feeds/refresh")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"created": 3})
        refresh_all.assert_called_once()
        self.assertNotIn("valid UUID", response.text)
        self.assertNotIn("found `r`", response.text)

    def test_collection_refresh_one_feed_uses_json_uuid(self):
        app, db, owner = _app()
        feed_id = uuid4()
        feed = SimpleNamespace(id=feed_id, user_id=owner.id, url="https://example.com/rss")
        db.get.return_value = feed
        with patch("app.routers.feeds.rss.refresh_feed", return_value=2) as refresh_one:
            client = TestClient(app)
            response = client.post("/api/v1/feeds/refresh", json={"feed_id": str(feed_id)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"created": 2})
        refresh_one.assert_called_once()
        self.assertEqual(db.get.call_args.args[1], feed_id)

    def test_word_refresh_in_uuid_slot_is_invalid_feed(self):
        app, _db, _owner = _app()
        client = TestClient(app)
        response = client.post("/api/v1/feeds/refresh/not-a-route")
        self.assertNotEqual(response.status_code, 200)
        posted = client.post("/api/v1/feeds/refresh", json={"feed_id": "refresh"})
        self.assertEqual(posted.status_code, 422)
        self.assertEqual(posted.json()["detail"], "Invalid feed")
        self.assertNotIn("found `r`", posted.text)
        path = client.post("/api/v1/feeds/refresh/refresh")
        self.assertIn(path.status_code, {404, 405, 422})
        if path.status_code == 422:
            self.assertEqual(path.json()["detail"], "Invalid feed")
            self.assertNotIn("pydantic", path.text.lower())

    def test_path_refresh_requires_uuid(self):
        app, _db, _owner = _app()
        client = TestClient(app)
        bad = client.post("/api/v1/feeds/refresh/refresh")
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(bad.json()["detail"], "Invalid feed")
        self.assertNotIn("found `r`", bad.text)
        slug = client.post("/api/v1/feeds/not-a-uuid/refresh")
        self.assertEqual(slug.status_code, 422)
        self.assertEqual(slug.json()["detail"], "Invalid feed")


if __name__ == "__main__":
    unittest.main()
