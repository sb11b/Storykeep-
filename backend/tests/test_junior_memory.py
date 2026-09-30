from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.database import get_db
from app.deps import get_current_user
from app.models import JuniorMemory, JuniorThread
from app.routers import junior_memory as memory_router
from app.routers import junior_shared as shared_router
from app.services import junior_memory as memory


class JuniorMemoryServiceTests(unittest.TestCase):
    def test_demo_never_attaches_or_saves(self):
        demo = SimpleNamespace(id=uuid.uuid4(), email="steve@storykeep.local", is_demo_locked=True)
        db = MagicMock()
        db.get.return_value = SimpleNamespace(markdown="# secret\nSteve only", updated_at=None)
        self.assertFalse(memory.can_use_memory(demo))
        self.assertIsNone(memory.system_section(db, demo))
        self.assertEqual(memory.markdown_for(db, demo), "")
        with self.assertRaises(HTTPException) as caught:
            memory.save_markdown(db, demo, "nope")
        self.assertEqual(caught.exception.status_code, 403)
        self.assertNotIn("secret", caught.exception.detail)

    def test_system_section_caps_at_8k(self):
        owner = SimpleNamespace(id=uuid.uuid4(), email="stevebitsko@duck.com", is_demo_locked=False)
        blob = "x" * (memory.MEMORY_ATTACH_CHARS + 400)
        db = MagicMock()
        db.get.return_value = SimpleNamespace(markdown=blob, updated_at=None)
        section = memory.system_section(db, owner)
        self.assertIsNotNone(section)
        assert section is not None
        self.assertIn("standing context", section.lower())
        self.assertTrue(section.endswith("…"))
        self.assertLessEqual(len(section), len(memory.MEMORY_SYSTEM_PREFIX) + memory.MEMORY_ATTACH_CHARS + 8)
        self.assertNotIn(blob, section)

    def test_seed_only_owner_when_empty(self):
        db = MagicMock()
        db.scalar.return_value = None
        memory.seed_steve_memory(db)
        db.add.assert_not_called()

        demo = SimpleNamespace(id=uuid.uuid4(), email="steve@storykeep.local", is_demo_locked=False)
        db.scalar.return_value = demo
        memory.seed_steve_memory(db)
        db.add.assert_not_called()

        owner = SimpleNamespace(id=uuid.uuid4(), email=memory.OWNER_EMAIL, is_demo_locked=False)
        db.scalar.return_value = owner
        db.get.return_value = None
        memory.seed_steve_memory(db)
        db.add.assert_called_once()
        row = db.add.call_args[0][0]
        self.assertIsInstance(row, JuniorMemory)
        self.assertEqual(row.user_id, owner.id)
        self.assertIn(memory.OWNER_EMAIL, row.markdown)
        self.assertIn("Do not dump", row.markdown)

        db.reset_mock()
        db.scalar.return_value = owner
        db.get.return_value = SimpleNamespace(markdown="# already kept", updated_at=None)
        memory.seed_steve_memory(db)
        db.add.assert_not_called()

    def test_append_keeps_original_text(self):
        owner = SimpleNamespace(id=uuid.uuid4(), email="stevebitsko@duck.com", is_demo_locked=False)
        row = SimpleNamespace(markdown="Keep this.", updated_at=None)
        db = MagicMock()
        db.get.return_value = row
        saved = memory.append_markdown(db, owner, "New paragraph")
        self.assertEqual(saved.markdown, "Keep this.\n\nNew paragraph")
        self.assertTrue(saved.markdown.startswith("Keep this."))
        with self.assertRaises(HTTPException) as caught:
            memory.append_markdown(db, owner, "  ")
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(row.markdown, "Keep this.\n\nNew paragraph")

    def test_save_rejects_oversize(self):
        owner = SimpleNamespace(id=uuid.uuid4(), email="stevebitsko@duck.com", is_demo_locked=False)
        db = MagicMock()
        db.get.return_value = None
        with self.assertRaises(HTTPException) as caught:
            memory.save_markdown(db, owner, "y" * (memory.MEMORY_SAVE_CHARS + 1))
        self.assertEqual(caught.exception.status_code, 400)


class JuniorMemoryRouterTests(unittest.TestCase):
    def test_demo_get_and_put_are_403(self):
        app = FastAPI()
        app.include_router(memory_router.router, prefix="/api/v1")
        demo = SimpleNamespace(id=uuid.uuid4(), email="steve@storykeep.local", is_demo_locked=True)

        def fake_db():
            yield MagicMock()

        app.dependency_overrides[get_db] = fake_db
        app.dependency_overrides[get_current_user] = lambda: demo
        client = TestClient(app)
        got = client.get("/api/v1/junior/memory")
        self.assertEqual(got.status_code, 403)
        self.assertNotIn("Steve", got.text)
        self.assertNotIn("markdown", got.text.lower() if got.status_code == 200 else "")
        put = client.put("/api/v1/junior/memory", json={"markdown": "# leaked"})
        self.assertEqual(put.status_code, 403)
        posted = client.post("/api/v1/junior/memory", json={"text": "leaked"})
        self.assertEqual(posted.status_code, 403)
        self.assertNotIn("leaked", posted.text)

    def test_post_appends_and_keeps_original(self):
        app = FastAPI()
        app.include_router(memory_router.router, prefix="/api/v1")
        row = SimpleNamespace(markdown="Original line", updated_at=None)
        db = MagicMock()
        db.get.return_value = row
        owner = SimpleNamespace(id=uuid.uuid4(), email="stevebitsko@duck.com", is_demo_locked=False)

        def fake_db():
            yield db

        app.dependency_overrides[get_db] = fake_db
        app.dependency_overrides[get_current_user] = lambda: owner
        client = TestClient(app)
        blank = client.post("/api/v1/junior/memory", json={"text": "   "})
        self.assertEqual(blank.status_code, 400)
        self.assertEqual(row.markdown, "Original line")
        added = client.post("/api/v1/junior/memory", json={"text": "Added line"})
        self.assertEqual(added.status_code, 200)
        self.assertEqual(added.json()["markdown"], "Original line\n\nAdded line")
        self.assertTrue(added.json()["markdown"].startswith("Original line"))


class JuniorThreadMemoryNoteRouterTests(unittest.TestCase):
    def _client(self, db, user) -> TestClient:
        app = FastAPI()
        app.include_router(shared_router.router, prefix="/api/v1")

        def fake_db():
            yield db

        app.dependency_overrides[get_db] = fake_db
        app.dependency_overrides[get_current_user] = lambda: user
        return TestClient(app)

    def test_missing_thread_is_404_and_does_not_append(self):
        owner = SimpleNamespace(id=uuid.uuid4(), email="stevebitsko@duck.com", is_demo_locked=False)
        note = SimpleNamespace(markdown="Keep this.", updated_at=None)
        db = MagicMock()
        db.get.side_effect = lambda model, key: note if model is JuniorMemory else None
        client = self._client(db, owner)
        thread_id = uuid.uuid4()
        got = client.get(f"/api/v1/junior/threads/{thread_id}/memory")
        self.assertEqual(got.status_code, 404)
        posted = client.post(
            f"/api/v1/junior/threads/{thread_id}/memory",
            json={"text": "nope"},
        )
        self.assertEqual(posted.status_code, 404)
        self.assertEqual(note.markdown, "Keep this.")
        db.commit.assert_not_called()

    def test_post_appends_on_owned_thread(self):
        owner_id = uuid.uuid4()
        owner = SimpleNamespace(id=owner_id, email="stevebitsko@duck.com", is_demo_locked=False)
        thread = SimpleNamespace(id=uuid.uuid4(), user_id=owner_id)
        note = SimpleNamespace(markdown="Keep this.", updated_at=None)
        db = MagicMock()

        def fake_get(model, key):
            if model is JuniorThread and key == thread.id:
                return thread
            if model is JuniorMemory:
                return note
            return None

        db.get.side_effect = fake_get
        client = self._client(db, owner)
        got = client.get(f"/api/v1/junior/threads/{thread.id}/memory")
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["markdown"], "Keep this.")
        posted = client.post(
            f"/api/v1/junior/threads/{thread.id}/memory",
            json={"text": "Added line"},
        )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()["markdown"], "Keep this.\n\nAdded line")
        self.assertTrue(posted.json()["markdown"].startswith("Keep this."))
        db.commit.assert_called()

    def test_demo_post_is_403(self):
        demo = SimpleNamespace(id=uuid.uuid4(), email="steve@storykeep.local", is_demo_locked=True)
        client = self._client(MagicMock(), demo)
        posted = client.post(
            f"/api/v1/junior/threads/{uuid.uuid4()}/memory",
            json={"text": "leaked"},
        )
        self.assertEqual(posted.status_code, 403)
        self.assertNotIn("leaked", posted.text)


if __name__ == "__main__":
    unittest.main()
