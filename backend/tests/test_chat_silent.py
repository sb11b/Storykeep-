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
        self.assertIsNone(captured.get("tools"))
        self.assertNotIn("code_interpreter", response.text)
        self.assertNotIn('"reasoning_effort": "xhigh"', response.text)
        self.assertIn('"stream_status": "working"', response.text)
        self.assertIn('"stream_status": "writing"', response.text)
        self.assertIn("Hi", response.text)

    def test_hello_skips_calendar_tools_when_connected(self):
        captured: dict = {}

        async def fake_stream(*_args, **kwargs):
            captured.update(kwargs)
            yield "Hi"

        app = _app()
        with (
            patch.object(chat_service, "require_key", return_value="xai-test"),
            patch.object(chat_service, "enforce_rate_limit"),
            patch("app.routers.chat.grok_store.should_persist", return_value=False),
            patch("app.routers.chat.calendars.is_connected", return_value=True),
            patch("app.routers.chat.is_locked", return_value=False),
            patch.object(chat_service, "stream_completion", fake_stream),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={"message": "hello", "model": "auto", "reasoning_effort": "auto"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(captured.get("tools"))
        self.assertEqual(captured.get("reasoning_effort"), "low")
        self.assertNotIn("code_interpreter", response.text)

    def test_summarize_unread_uses_mail_list_and_low(self):
        captured: dict = {}

        async def fake_stream(*_args, **kwargs):
            captured.update(kwargs)
            yield "Two unread."

        app = _app()
        with (
            patch.object(chat_service, "require_key", return_value="xai-test"),
            patch.object(chat_service, "enforce_rate_limit"),
            patch("app.routers.chat.grok_store.should_persist", return_value=False),
            patch("app.routers.chat.mail_service.has_token", return_value=True),
            patch("app.routers.chat.mail_service.require_token", return_value="fmu1-test-token-not-real"),
            patch(
                "app.routers.chat.jmap.list_emails",
                return_value={
                    "items": [
                        {"from": "Ada", "subject": "Hi", "date": "2026-09-15T12:00:00Z", "unseen": True}
                    ]
                },
            ),
            patch.object(chat_service, "stream_completion", fake_stream),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={"message": "summarize unread", "model": "auto", "reasoning_effort": "auto"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured.get("model"), "grok-4.6")
        self.assertEqual(captured.get("reasoning_effort"), "low")
        extra = captured.get("extra_system") or ""
        self.assertIn("Ada", extra)
        self.assertIn("cap 50", extra)
        tools = captured.get("tools")
        self.assertTrue(
            tools is None
            or all((item.get("function") or {}).get("name") != "propose_send_mail" for item in tools)
        )

    def test_summarize_unread_uses_mail_list_and_low(self):
        captured: dict = {}

        async def fake_stream(*_args, **kwargs):
            captured.update(kwargs)
            yield "Two unread."

        app = _app()
        with (
            patch.object(chat_service, "require_key", return_value="xai-test"),
            patch.object(chat_service, "enforce_rate_limit"),
            patch("app.routers.chat.grok_store.should_persist", return_value=False),
            patch("app.routers.chat.mail_service.has_token", return_value=True),
            patch("app.routers.chat.mail_service.require_token", return_value="fmu1-test-token-not-real"),
            patch(
                "app.routers.chat.jmap.list_emails",
                return_value={
                    "items": [
                        {"from": "Ada", "subject": "Hi", "date": "2026-09-15T12:00:00Z", "unseen": True}
                    ]
                },
            ),
            patch.object(chat_service, "stream_completion", fake_stream),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={"message": "summarize unread", "model": "auto", "reasoning_effort": "auto"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured.get("model"), "grok-4.6")
        self.assertEqual(captured.get("reasoning_effort"), "low")
        extra = captured.get("extra_system") or ""
        self.assertIn("Ada", extra)
        self.assertIn("cap 50", extra)
        tools = captured.get("tools")
        self.assertTrue(
            tools is None
            or all((item.get("function") or {}).get("name") != "propose_send_mail" for item in tools)
        )

    def test_summarize_unread_uses_mail_list_and_low(self):
        captured: dict = {}

        async def fake_stream(*_args, **kwargs):
            captured.update(kwargs)
            yield "Two unread."

        app = _app()
        with (
            patch.object(chat_service, "require_key", return_value="xai-test"),
            patch.object(chat_service, "enforce_rate_limit"),
            patch("app.routers.chat.grok_store.should_persist", return_value=False),
            patch("app.routers.chat.mail_service.has_token", return_value=True),
            patch("app.routers.chat.mail_service.require_token", return_value="fmu1-test-token-not-real"),
            patch(
                "app.routers.chat.jmap.list_emails",
                return_value={
                    "items": [
                        {"from": "Ada", "subject": "Hi", "date": "2026-09-15T12:00:00Z", "unseen": True}
                    ]
                },
            ),
            patch.object(chat_service, "stream_completion", fake_stream),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={"message": "summarize unread", "model": "auto", "reasoning_effort": "auto"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured.get("model"), "grok-4.6")
        self.assertEqual(captured.get("reasoning_effort"), "low")
        extra = captured.get("extra_system") or ""
        self.assertIn("Ada", extra)
        self.assertIn("cap 50", extra)
        tools = captured.get("tools")
        self.assertTrue(tools is None or all((t.get("function") or {}).get("name") != "propose_send_mail" for t in tools))

    def test_empty_tool_turn_retries_without_tools(self):
        calls: list[object] = []

        async def fake_stream(*_args, **kwargs):
            calls.append(kwargs.get("tools"))
            if kwargs.get("tools"):
                if False:
                    yield ""  # pragma: no cover
                return
            yield "Here is a real reply."

        app = _app()
        with (
            patch.object(chat_service, "require_key", return_value="xai-test"),
            patch.object(chat_service, "enforce_rate_limit"),
            patch("app.routers.chat.grok_store.should_persist", return_value=False),
            patch("app.routers.chat.search_tool.owner_can_search", return_value=True),
            patch("app.routers.chat.search_tool.wants_web_search", return_value=False),
            patch.object(chat_service, "stream_completion", fake_stream),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={"message": "What is a Python list?", "model": "auto", "reasoning_effort": "auto"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(calls), 2)
        self.assertTrue(calls[0])
        self.assertIsNone(calls[-1])
        self.assertIn("Here is a real reply.", response.text)
        self.assertNotIn("returned no text", response.text)

    def test_empty_xai_stream_emits_fallback_not_bare_error(self):
        async def empty(*_args, **_kwargs):
            if False:
                yield ""  # pragma: no cover

        app = _app()
        with (
            patch.object(chat_service, "require_key", return_value="xai-test"),
            patch.object(chat_service, "enforce_rate_limit"),
            patch("app.routers.chat.grok_store.should_persist", return_value=False),
            patch.object(chat_service, "stream_completion", empty),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={"message": "hello", "model": "auto", "reasoning_effort": "auto"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn(chat_service.EMPTY_REPLY_FALLBACK, response.text)
        self.assertIn("data: [DONE]", response.text)
        self.assertNotIn("returned no text", response.text)

    def test_empty_piece_after_connect_is_thinking(self):
        async def fake_stream(*_args, **kwargs):
            yield ""
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
        self.assertIn('"stream_status": "working"', response.text)
        self.assertIn('"stream_status": "thinking"', response.text)
        self.assertIn('"stream_status": "writing"', response.text)
        working_at = response.text.index('"stream_status": "working"')
        thinking_at = response.text.index('"stream_status": "thinking"')
        writing_at = response.text.index('"stream_status": "writing"')
        self.assertLess(working_at, thinking_at)
        self.assertLess(thinking_at, writing_at)

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


class StreamConnectStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_xai_http_200_yields_empty_before_tokens(self):
        class FakeResponse:
            status_code = 200

            def aiter_lines(self):
                async def lines():
                    yield 'data: {"choices":[{"delta":{"content":"Hi"}}]}'

                return lines()

        class FakeStream:
            async def __aenter__(self):
                return FakeResponse()

            async def __aexit__(self, *_args):
                return False

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            def stream(self, *args, **kwargs):
                return FakeStream()

        with (
            patch.object(chat_service, "require_key", return_value="xai-test"),
            patch.object(chat_service.httpx, "AsyncClient", FakeClient),
        ):
            pieces: list[str] = []
            async for piece in chat_service.stream_completion(
                [{"role": "user", "content": "hello"}],
                None,
                include_article=False,
                model="grok-4.6",
            ):
                pieces.append(piece)
        self.assertEqual(pieces[0], "")
        self.assertEqual(pieces[1], "Hi")


class CursorStartPayloadTests(unittest.TestCase):
    def test_start_agent_can_read_pane_name(self):
        from app.services import cursor_agent_tool

        app = _app()
        outcome = cursor_agent_tool.CursorAgentOutcome(
            True,
            "Cursor Cloud Agent started.",
            200,
            "agent-1",
            "https://cursor.com/agents/agent-1",
            "run-1",
        )
        with (
            patch.object(chat_service, "require_key", return_value="xai-test"),
            patch.object(chat_service, "enforce_rate_limit"),
            patch("app.routers.chat.grok_store.should_persist", return_value=False),
            patch("app.routers.chat.cursor_agent_tool.start_agent", return_value=outcome),
            patch("app.routers.chat.cursor_agent_tool.owner_can_use", return_value=True),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={
                    "message": "start a cursor agent to fix the mail list",
                    "model": "auto",
                    "reasoning_effort": "auto",
                    "pane_name": "Storykeep",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("cannot access local variable", response.text)
        self.assertIn("Cursor Cloud Agent started", response.text)
        self.assertIn("https://cursor.com/agents/agent-1", response.text)


if __name__ == "__main__":
    unittest.main()
