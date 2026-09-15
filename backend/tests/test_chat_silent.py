from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import get_db
from app.deps import get_current_user
from app.main import http_exception_with_message
from app.routers import chat as chat_router
from app.services import chat as chat_service


def _app() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(StarletteHTTPException, http_exception_with_message)
    app.include_router(chat_router.router, prefix="/api/v1")
    user = SimpleNamespace(
        id=uuid.uuid4(),
        email="stevebitsko@duck.com",
        is_demo_locked=False,
    )

    def fake_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_user] = lambda: user
    return app


class ChatSilentGateTests(unittest.TestCase):
    def test_silent_xai_streams_working_then_error(self):
        async def silent(*_args, **_kwargs):
            raise HTTPException(status_code=504, detail=chat_service.XAI_SILENT_DETAIL)
            yield ""  # pragma: no cover

        app = _app()
        with (
            patch.object(chat_service, "require_key", return_value="xai-test"),
            patch.object(chat_service, "enforce_rate_limit"),
            patch("app.routers.chat.grok_store.should_persist", return_value=False),
            patch.object(chat_service, "stream_completion", silent),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={"message": "hello", "model": "auto", "reasoning_effort": "auto"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))
        self.assertIn('"stream_status": "working"', response.text)
        self.assertIn('"reasoning_effort": "low"', response.text)
        self.assertIn("xAI silent", response.text)

    def test_hello_auto_sends_grok46_low(self):
        captured: dict = {}

        async def fake_stream(*_args, **kwargs):
            captured.update(kwargs)
            yield "Hi"

        app = _app()
        with (
            patch.object(chat_service, "require_key", return_value="xai-test"),
            patch.object(chat_service, "enforce_rate_limit"),
            patch("app.routers.chat.grok_store.should_persist", return_value=False),
            patch.object(chat_service, "stream_completion", fake_stream),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={"message": "hello", "model": "auto", "reasoning_effort": "auto"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers.get("content-type", ""))
        self.assertEqual(captured.get("model"), "grok-4.6")
        self.assertEqual(captured.get("reasoning_effort"), "low")
        self.assertIn('"stream_status": "working"', response.text)
        self.assertIn('"stream_status": "writing"', response.text)
        self.assertIn("Hi", response.text)

    def test_morning_auto_sends_grok46_low(self):
        captured: dict = {}

        async def fake_stream(*_args, **kwargs):
            captured.update(kwargs)
            yield "Fine"

        app = _app()
        with (
            patch.object(chat_service, "require_key", return_value="xai-test"),
            patch.object(chat_service, "enforce_rate_limit"),
            patch("app.routers.chat.grok_store.should_persist", return_value=False),
            patch.object(chat_service, "stream_completion", fake_stream),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={"message": "how was your morning", "model": "auto", "reasoning_effort": "auto"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured.get("model"), "grok-4.6")
        self.assertEqual(captured.get("reasoning_effort"), "low")
        self.assertNotIn("code_interpreter", response.text)
        self.assertIn('"reasoning_effort": "low"', response.text)

    def test_chat_health_includes_xai_status(self):
        app = _app()
        payload = {
            "ok": True,
            "model": "grok-4.6",
            "reasoning": "low",
            "ttft_ms": 120,
            "xai_status": 200,
        }
        with (
            patch.object(chat_service, "key_configured", return_value=True),
            patch.object(chat_service, "ping_xai", return_value=payload),
        ):
            client = TestClient(app)
            response = client.get("/api/v1/chat/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)

    def test_chat_health_no_key_includes_xai_status(self):
        app = _app()
        with patch.object(chat_service, "key_configured", return_value=False):
            client = TestClient(app)
            response = client.get("/api/v1/chat/health")
        body = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(body["ok"])
        self.assertEqual(body["model"], "grok-4.6")
        self.assertEqual(body["reasoning"], "low")
        self.assertIn("xai_status", body)
        self.assertIsNone(body["xai_status"])


if __name__ == "__main__":
    unittest.main()
