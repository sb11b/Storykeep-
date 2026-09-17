from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import get_db
from app.deps import get_current_user
from app.main import http_exception_with_message, request_validation_handler
from app.routers import chat as chat_router
from app.services import grok_conversations as grok_store
from app.services.demo_lock import is_locked


def _app(user=None):
    app = FastAPI()
    app.add_exception_handler(StarletteHTTPException, http_exception_with_message)
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.include_router(chat_router.router, prefix="/api/v1")
    owner = user or SimpleNamespace(id=uuid4(), email="reader@example.com", is_demo_locked=False)
    db = MagicMock()

    def fake_db():
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_user] = lambda: owner
    return app, db, owner


def _row(owner, conversation_id=None):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=conversation_id or uuid4(),
        user_id=owner.id,
        title="New chat",
        pane=None,
        model="auto",
        last_model=None,
        reasoning="auto",
        last_reasoning=None,
        recap_question=False,
        saved_note_id=None,
        created_at=now,
        updated_at=now,
    )


class ChatCreateRouteTests(unittest.TestCase):
    def test_create_is_collection_post_not_a_uuid_slot(self):
        app, db, owner = _app()
        row = _row(owner)
        with (
            patch.object(grok_store, "should_persist", return_value=True),
            patch.object(grok_store, "create_conversation", return_value=row) as create,
            patch("app.routers.chat.chat_service.stream_completion") as stream,
            patch("app.routers.chat.chat_service.require_key") as require_key,
        ):
            client = TestClient(app)
            response = client.post("/api/v1/chat/conversations", json={})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], str(row.id))
        create.assert_called_once()
        stream.assert_not_called()
        require_key.assert_not_called()
        db.commit.assert_called()
        self.assertNotIn("valid UUID", response.text)
        self.assertNotIn("found `n`", response.text)

    def test_create_reuses_client_id(self):
        app, _db, owner = _app()
        conversation_id = uuid4()
        row = _row(owner, conversation_id)
        with (
            patch.object(grok_store, "should_persist", return_value=True),
            patch.object(grok_store, "create_conversation", return_value=row) as create,
        ):
            client = TestClient(app)
            first = client.post("/api/v1/chat/conversations", json={"id": str(conversation_id)})
            second = client.post("/api/v1/chat/conversations", json={"id": str(conversation_id)})
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.json()["id"], str(conversation_id))
        self.assertEqual(second.json()["id"], str(conversation_id))
        self.assertEqual(create.call_count, 2)
        self.assertEqual(create.call_args.kwargs["conversation_id"], conversation_id)

    def test_word_new_in_uuid_slot_is_invalid_chat(self):
        app, _db, _owner = _app()
        client = TestClient(app)
        response = client.get("/api/v1/chat/conversations/new")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Invalid chat")
        self.assertNotIn("found `n`", response.text)
        self.assertNotIn("pydantic", response.text.lower())
        refresh = client.get("/api/v1/chat/conversations/refresh")
        self.assertEqual(refresh.status_code, 422)
        self.assertEqual(refresh.json()["detail"], "Invalid chat")
        titled = client.get("/api/v1/chat/conversations/Hello")
        self.assertEqual(titled.status_code, 422)
        self.assertEqual(titled.json()["detail"], "Invalid chat")

    def test_create_rejects_non_uuid_id_in_body(self):
        app, _db, _owner = _app()
        client = TestClient(app)
        response = client.post("/api/v1/chat/conversations", json={"id": "new"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Invalid chat")
        self.assertNotIn("found `n`", response.text)

    def test_locked_demo_cannot_create(self):
        demo = SimpleNamespace(id=uuid4(), email="steve@storykeep.local", is_demo_locked=True)
        self.assertTrue(is_locked(demo))
        app, _db, _owner = _app(demo)
        client = TestClient(app)
        response = client.post("/api/v1/chat/conversations", json={})
        self.assertEqual(response.status_code, 403)


class CreateConversationIdempotencyTests(unittest.TestCase):
    def test_existing_row_is_returned_without_insert(self):
        user_id = uuid4()
        conversation_id = uuid4()
        user = SimpleNamespace(id=user_id)
        existing = SimpleNamespace(id=conversation_id, user_id=user_id, title="New chat")
        db = MagicMock()
        db.scalar.return_value = existing
        row = grok_store.create_conversation(db, user, conversation_id=conversation_id)
        self.assertIs(row, existing)
        db.add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
