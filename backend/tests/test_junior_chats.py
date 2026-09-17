from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.deps import get_current_user
from app.routers import junior_chats as chats_router


def _app(user=None):
    app = FastAPI()
    app.include_router(chats_router.router, prefix="/api/v1")
    owner = user or SimpleNamespace(id=uuid.uuid4(), email="stevebitsko@duck.com", is_demo_locked=False)

    def fake_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_user] = lambda: owner
    return app


class JuniorChatsRouteTests(unittest.TestCase):
    def test_unauthenticated_401(self):
        app = FastAPI()
        app.include_router(chats_router.router, prefix="/api/v1")
        client = TestClient(app)
        response = client.get("/api/v1/junior/chats")
        self.assertEqual(response.status_code, 401)

    def test_list_chats_returns_index_rows(self):
        cid = str(uuid.uuid4())
        note_id = str(uuid.uuid4())
        app = _app()
        with patch(
            "app.routers.junior_chats.chat_index.chats_for",
            return_value=[
                {
                    "id": cid,
                    "date": "2026-09-17",
                    "title": "DAT lists",
                    "summary": "Explain Python lists",
                    "note_id": note_id,
                    "messages": 4,
                }
            ],
        ):
            client = TestClient(app)
            response = client.get("/api/v1/junior/chats")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["id"], cid)
        self.assertEqual(body[0]["title"], "DAT lists")
        self.assertEqual(body[0]["note_id"], note_id)
        self.assertEqual(body[0]["messages"], 4)

    def test_demo_gets_empty_list(self):
        app = _app(SimpleNamespace(id=uuid.uuid4(), email="steve@storykeep.local", is_demo_locked=True))
        with patch("app.routers.junior_chats.chat_index.chats_for", return_value=[]):
            client = TestClient(app)
            response = client.get("/api/v1/junior/chats")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])


if __name__ == "__main__":
    unittest.main()
