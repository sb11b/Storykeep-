from __future__ import annotations

import time
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import get_db
from app.deps import get_current_user
from app.main import http_exception_with_message
from app.routers import chat as chat_router


def _app() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(StarletteHTTPException, http_exception_with_message)
    app.include_router(chat_router.router, prefix="/api/v1")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    user = SimpleNamespace(id=uuid.uuid4(), email="stevebitsko@duck.com", is_demo_locked=False)

    def fake_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_user] = lambda: user
    return app


class ChatSetupStallTests(unittest.TestCase):
    """A blocked DB call in chat setup must not hold the worker or the spinner."""

    def test_stalled_setup_returns_504_message(self):
        def stalls(*_args, **_kwargs):
            time.sleep(2)
            raise AssertionError("setup should have been abandoned")

        app = _app()
        with (
            patch.object(chat_router, "CHAT_SETUP_BUDGET_SEC", 0.2),
            patch.object(chat_router, "_chat", stalls),
        ):
            client = TestClient(app)
            response = client.post("/api/v1/chat", json={"message": "hello"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))
        self.assertIn('"status": 504', response.text)
        self.assertIn('"message"', response.text)
        self.assertIn("stalled at", response.text)

    def test_stalled_setup_leaves_worker_responsive(self):
        def stalls(*_args, **_kwargs):
            time.sleep(1.5)
            raise AssertionError("setup should have been abandoned")

        app = _app()
        with (
            patch.object(chat_router, "CHAT_SETUP_BUDGET_SEC", 0.2),
            patch.object(chat_router, "_chat", stalls),
        ):
            client = TestClient(app)
            client.post("/api/v1/chat", json={"message": "hello"})
            health = client.get("/health")

        self.assertEqual(health.status_code, 200)

    def test_setup_stage_names_last_step(self):
        stage = chat_router._SetupStage()
        self.assertEqual(stage.name, "start")
        stage.mark("calendar")
        self.assertEqual(stage.name, "calendar")
        self.assertGreaterEqual(stage.elapsed_ms(), 0)


if __name__ == "__main__":
    unittest.main()
