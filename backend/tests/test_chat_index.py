from __future__ import annotations

import unittest
import uuid
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import get_db
from app.deps import get_current_user
from app.main import http_exception_with_message
from app.routers import chat as chat_router
from app.services import chat as chat_service
from app.services import chat_index
from app.services import web_search


def _app(user=None):
    app = FastAPI()
    app.add_exception_handler(StarletteHTTPException, http_exception_with_message)
    app.include_router(chat_router.router, prefix="/api/v1")

    def fake_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = fake_db
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return app


def _owner():
    return SimpleNamespace(id=uuid.uuid4(), email="stevebitsko@duck.com", is_demo_locked=False)


def _demo():
    return SimpleNamespace(id=uuid.uuid4(), email="steve@storykeep.local", is_demo_locked=True)


@contextmanager
def _stream_patches(fake_stream):
    with ExitStack() as stack:
        stack.enter_context(patch.object(chat_service, "require_key", return_value="xai-test"))
        stack.enter_context(patch.object(chat_service, "enforce_rate_limit"))
        stack.enter_context(patch("app.routers.chat.grok_store.should_persist", return_value=False))
        stack.enter_context(patch("app.routers.chat.calendars.is_connected", return_value=False))
        stack.enter_context(patch("app.routers.chat.mail_service.has_token", return_value=False))
        stack.enter_context(patch("app.routers.chat.junior_memory.system_section", return_value=None))
        stack.enter_context(patch.object(web_search, "configured", return_value=False))
        stack.enter_context(patch.object(chat_service, "stream_completion", fake_stream))
        yield


class ChatIndexUnitTests(unittest.TestCase):
    def test_wants_index_and_read(self):
        self.assertTrue(chat_index.wants_index("all chats"))
        self.assertTrue(chat_index.wants_index("catch me up"))
        self.assertTrue(chat_index.wants_read("read this chat"))
        self.assertFalse(chat_index.wants_index("hello"))
        self.assertFalse(chat_index.wants_read("hello"))

    def test_demo_cannot_use(self):
        self.assertTrue(chat_index.can_use(_owner()))
        self.assertFalse(chat_index.can_use(_demo()))

    def test_format_index_does_not_invent(self):
        empty = chat_index.format_index([])
        self.assertIn("None.", empty)
        cid = str(uuid.uuid4())
        text = chat_index.format_index(
            [
                {
                    "id": cid,
                    "date": "2026-09-17",
                    "title": "DAT lists",
                    "summary": "Explain Python lists",
                    "note_id": None,
                    "messages": 4,
                }
            ]
        )
        self.assertIn(cid, text)
        self.assertIn("DAT lists", text)
        self.assertIn("note=none", text)
        self.assertNotIn("invent", text.lower().split("do not invent")[0][-20:])

    def test_format_slice_marks_truncation(self):
        cid = str(uuid.uuid4())
        text = chat_index.format_slice(
            {
                "id": cid,
                "title": "DAT lists",
                "note_id": None,
                "offset": 0,
                "next_offset": 8,
                "total": 20,
                "turns": [{"role": "user", "content": "Explain lists"}],
            }
        )
        self.assertIn("Truncated", text)
        self.assertIn("offset=8", text)
        self.assertIn("Steve: Explain lists", text)

    def test_assemble_read_tool(self):
        cid = uuid.uuid4()
        call = chat_index.assemble_tool_call(
            [
                {
                    "index": 0,
                    "function": {
                        "name": "read_chat",
                        "arguments": f'{{"conversation_id":"{cid}","offset":8}}',
                    },
                }
            ]
        )
        self.assertEqual(call["name"], "read_chat")
        self.assertEqual(call["conversation_id"], cid)
        self.assertEqual(call["offset"], 8)


class ChatIndexRouteTests(unittest.TestCase):
    def test_hello_does_not_attach_chat_tools(self):
        captured: dict = {}

        async def fake_stream(*_args, **kwargs):
            captured.update(kwargs)
            yield "Hi"

        app = _app(_owner())
        with _stream_patches(fake_stream):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={"message": "hello", "model": "auto", "reasoning_effort": "auto"},
            )
        self.assertEqual(response.status_code, 200)
        names = []
        for item in captured.get("tools") or []:
            fn = item.get("function") if isinstance(item.get("function"), dict) else {}
            names.append(fn.get("name") or item.get("name"))
        self.assertNotIn("list_chats", names)
        self.assertNotIn("read_chat", names)

    def test_catch_me_up_attaches_index(self):
        captured: dict = {}
        cid = str(uuid.uuid4())

        async def fake_stream(*_args, **kwargs):
            captured.update(kwargs)
            yield "Index first."

        app = _app(_owner())
        with (
            _stream_patches(fake_stream),
            patch(
                "app.routers.chat.chat_index.build_index",
                return_value=[
                    {
                        "id": cid,
                        "date": "2026-09-17",
                        "title": "DAT lists",
                        "summary": "Explain Python lists",
                        "note_id": None,
                        "messages": 2,
                    }
                ],
            ),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={"message": "catch me up", "model": "auto", "reasoning_effort": "auto"},
            )
        self.assertEqual(response.status_code, 200)
        extra = captured.get("extra_system") or ""
        self.assertIn("Junior chat index", extra)
        self.assertIn(cid, extra)
        self.assertIn("DAT lists", extra)
        names = []
        for item in captured.get("tools") or []:
            fn = item.get("function") if isinstance(item.get("function"), dict) else {}
            names.append(fn.get("name") or item.get("name"))
        self.assertIn("list_chats", names)
        self.assertIn("read_chat", names)

    def test_read_this_chat_needs_id(self):
        captured: dict = {}

        async def fake_stream(*_args, **kwargs):
            captured.update(kwargs)
            yield "Which id?"

        app = _app(_owner())
        with _stream_patches(fake_stream):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={"message": "read this chat", "model": "auto"},
            )
        self.assertEqual(response.status_code, 200)
        extra = captured.get("extra_system") or ""
        self.assertIn("did not give a conversation id", extra)

    def test_read_this_chat_with_id_attaches_slice(self):
        captured: dict = {}
        cid = uuid.uuid4()

        async def fake_stream(*_args, **kwargs):
            captured.update(kwargs)
            yield "That thread."

        app = _app(_owner())
        with (
            _stream_patches(fake_stream),
            patch(
                "app.routers.chat.chat_index.read_slice",
                return_value={
                    "id": str(cid),
                    "title": "DAT lists",
                    "note_id": None,
                    "offset": 0,
                    "next_offset": None,
                    "total": 1,
                    "turns": [{"role": "user", "content": "Explain lists"}],
                },
            ),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={"message": f"read this chat {cid}", "model": "auto"},
            )
        self.assertEqual(response.status_code, 200)
        extra = captured.get("extra_system") or ""
        self.assertIn("Junior chat slice", extra)
        self.assertIn("Explain lists", extra)
        self.assertIn(str(cid), extra)


class ChatIndexKeepOnShortTurnTests(unittest.TestCase):
    def test_short_turn_keeps_chat_tools(self):
        from app.services.chat_index import is_chat_index_tool
        from app.services.web_search import is_web_search_tool

        tools = [chat_index.LIST_CHATS_TOOL, web_search.WEB_SEARCH_TOOL]
        kept = [item for item in tools if is_web_search_tool(item) or is_chat_index_tool(item)]
        self.assertEqual(len(kept), 2)


if __name__ == "__main__":
    unittest.main()
