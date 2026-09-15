from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.database import get_db
from app.deps import get_current_user
from app.models import JuniorMemory
from app.routers import junior_memory as memory_router
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


if __name__ == "__main__":
    unittest.main()
