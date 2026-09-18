from __future__ import annotations

import json
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


class WebSearchClientTests(unittest.TestCase):
    def test_wants_lookup_queries(self):
        self.assertTrue(web_search.wants_web_search("what's the NFL score format / current UTC date source"))
        self.assertTrue(web_search.wants_web_search("look this up: grok-4.6 docs"))
        self.assertTrue(web_search.wants_web_search("current bitcoin price"))
        self.assertFalse(web_search.wants_web_search("hello"))
        self.assertFalse(web_search.wants_web_search("thanks"))

    def test_missing_key_is_unavailable_not_cannot_search(self):
        with patch.object(web_search.settings, "xai_api_key", ""):
            with self.assertLogs("app.services.web_search", level="WARNING") as logs:
                outcome = web_search.search("nfl scores")
        self.assertTrue(outcome.fatal)
        self.assertEqual(outcome.status_code, 503)
        self.assertEqual(outcome.detail, web_search.UI_UNAVAILABLE)
        self.assertEqual(outcome.toast, web_search.UI_UNAVAILABLE)
        self.assertTrue(any(web_search.LOG_NOT_CONFIGURED in line for line in logs.output))
        self.assertNotIn("can't search", outcome.detail.lower())
        self.assertNotIn("cannot search", outcome.detail.lower())

    def test_extract_hits_titles_urls_snippets_no_html(self):
        body = {
            "output": [
                {
                    "type": "web_search_call",
                    "status": "completed",
                    "action": {
                        "type": "search",
                        "results": [
                            {
                                "title": "NFL Scoreboard",
                                "url": "https://www.espn.com/nfl/scoreboard",
                                "snippet": "<b>Live</b> scores",
                            },
                            {
                                "title": "UTC",
                                "url": "https://www.timeanddate.com/worldclock/timezone/utc",
                                "snippet": "Coordinated Universal Time",
                            },
                            {
                                "title": "Paywall",
                                "url": "https://www.ucertify.com/chapter",
                                "snippet": "login required",
                            },
                        ],
                    },
                }
            ]
        }
        hits = web_search.extract_hits(body)
        urls = [hit.url for hit in hits]
        self.assertIn("https://www.espn.com/nfl/scoreboard", urls)
        self.assertIn("https://www.timeanddate.com/worldclock/timezone/utc", urls)
        self.assertNotIn("https://www.ucertify.com/chapter", urls)
        self.assertEqual(hits[0].snippet, "Live scores")
        self.assertNotIn("<", hits[0].snippet)

    def test_extract_hits_json_array_capped(self):
        rows = [
            {"title": f"T{i}", "url": f"https://example.com/{i}", "snippet": f"s{i}"}
            for i in range(8)
        ]
        body = {"output_text": json.dumps(rows)}
        hits = web_search.extract_hits(body)
        self.assertEqual(len(hits), 5)
        self.assertEqual(hits[0].url, "https://example.com/0")

    def test_retry_once_on_quota_then_fail_with_status(self):
        calls = {"n": 0}

        class FakeResponse:
            status_code = 429
            text = '{"error":{"message":"quota exceeded"}}'

            def json(self):
                return {"error": {"message": "quota exceeded"}}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, *args, **kwargs):
                calls["n"] += 1
                return FakeResponse()

        with (
            patch.object(web_search.settings, "xai_api_key", "xai-test-key"),
            patch("app.services.web_search.httpx.Client", FakeClient),
        ):
            outcome = web_search.search("current utc date")
        self.assertGreaterEqual(calls["n"], 2)
        self.assertTrue(outcome.fatal)
        self.assertEqual(outcome.status_code, 429)
        self.assertIn("HTTP 429", outcome.detail)
        self.assertIn("quota", outcome.detail.lower())
        self.assertNotIn("can't search", outcome.detail.lower())

    def test_format_hits_for_model(self):
        text = web_search.format_hits_for_model(
            [web_search.SearchHit("ESPN NFL", "https://www.espn.com/nfl/scoreboard", "scores")]
        )
        self.assertIn("[ESPN NFL](https://www.espn.com/nfl/scoreboard)", text)
        self.assertNotIn("<html", text.lower())


class WebSearchRouteTests(unittest.TestCase):
    def test_unauthenticated_401(self):
        app = _app()
        client = TestClient(app)
        response = client.post("/api/v1/search", json={"query": "nfl"})
        self.assertEqual(response.status_code, 401)

    def test_demo_403_no_tool(self):
        app = _app(_demo())
        client = TestClient(app)
        response = client.post("/api/v1/search", json={"query": "nfl"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Demo account closed")
        self.assertFalse(web_search.owner_can_search(_demo()))

    def test_missing_key_unavailable_copy(self):
        app = _app(_owner())
        with patch.object(web_search.settings, "xai_api_key", ""):
            client = TestClient(app)
            response = client.post("/api/v1/search", json={"query": "current utc date"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], web_search.UI_UNAVAILABLE)
        self.assertNotIn("cannot search", response.text.lower())
        self.assertNotIn("forever", response.text.lower())


class ChatSearchAttachTests(unittest.TestCase):
    def test_hello_does_not_attach_search_tool(self):
        captured: dict = {}

        async def fake_stream(*_args, **kwargs):
            captured.update(kwargs)
            yield "Hi"

        from app.services import chat as chat_service

        app = _app(_owner())
        with (
            patch.object(chat_service, "require_key", return_value="xai-test"),
            patch.object(chat_service, "enforce_rate_limit"),
            patch("app.routers.chat.grok_store.should_persist", return_value=False),
            patch("app.routers.chat.calendars.is_connected", return_value=False),
            patch("app.routers.chat.mail_service.has_token", return_value=False),
            patch("app.routers.chat.junior_memory.system_section", return_value=None),
            patch.object(web_search, "configured", return_value=True),
            patch.object(chat_service, "stream_completion", fake_stream),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={"message": "hello", "model": "auto", "reasoning_effort": "auto"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(captured.get("tools"))
        self.assertNotIn("searching", response.text)

    def test_lookup_turn_searches_and_cites(self):
        captured: dict = {}

        async def fake_stream(*_args, **kwargs):
            captured.update(kwargs)
            yield "NFL scores: [NFL Scoreboard](https://www.espn.com/nfl/scoreboard). UTC: [Time and Date](https://www.timeanddate.com/worldclock/timezone/utc)."

        hits = web_search.SearchOutcome(
            hits=(
                web_search.SearchHit("NFL Scoreboard", "https://www.espn.com/nfl/scoreboard", "live scores"),
                web_search.SearchHit(
                    "UTC time",
                    "https://www.timeanddate.com/worldclock/timezone/utc",
                    "Coordinated Universal Time",
                ),
            ),
            empty=False,
            toast=None,
            fatal=False,
            status_code=200,
            detail="",
        )
        from app.services import chat as chat_service

        app = _app(_owner())
        with (
            patch.object(chat_service, "require_key", return_value="xai-test"),
            patch.object(chat_service, "enforce_rate_limit"),
            patch("app.routers.chat.grok_store.should_persist", return_value=False),
            patch("app.routers.chat.calendars.is_connected", return_value=False),
            patch("app.routers.chat.mail_service.has_token", return_value=False),
            patch("app.routers.chat.junior_memory.system_section", return_value=None),
            patch.object(web_search, "configured", return_value=True),
            patch.object(web_search, "search", return_value=hits),
            patch.object(chat_service, "stream_completion", fake_stream),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={
                    "message": "what's the NFL score format / current UTC date source",
                    "model": "auto",
                    "reasoning_effort": "auto",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn('"stream_status": "searching"', response.text)
        extra = captured.get("extra_system") or ""
        self.assertIn("https://www.espn.com/nfl/scoreboard", extra)
        self.assertIn("https://www.timeanddate.com/worldclock/timezone/utc", extra)
        names = []
        for item in captured.get("tools") or []:
            fn = item.get("function") if isinstance(item.get("function"), dict) else {}
            names.append(fn.get("name") or item.get("name") or item.get("type"))
        self.assertIn("web_search", names)
        self.assertIn("espn.com/nfl/scoreboard", response.text)
        self.assertIn("timeanddate.com", response.text)

    def test_demo_chat_is_rejected(self):
        app = _app(_demo())
        client = TestClient(app)
        response = client.post(
            "/api/v1/chat",
            json={"message": "look this up: nfl scores", "model": "auto", "reasoning_effort": "auto"},
        )
        self.assertEqual(response.status_code, 403)

    def test_empty_hits_toast_and_training_fallback(self):
        captured: dict = {}

        async def fake_stream(*_args, **kwargs):
            captured.update(kwargs)
            yield "No public hits; answering from training."

        empty = web_search.SearchOutcome(
            (), True, web_search.EMPTY_TOAST, False, 200, web_search.EMPTY_TOAST
        )
        from app.services import chat as chat_service

        app = _app(_owner())
        with (
            patch.object(chat_service, "require_key", return_value="xai-test"),
            patch.object(chat_service, "enforce_rate_limit"),
            patch("app.routers.chat.grok_store.should_persist", return_value=False),
            patch("app.routers.chat.calendars.is_connected", return_value=False),
            patch("app.routers.chat.mail_service.has_token", return_value=False),
            patch("app.routers.chat.junior_memory.system_section", return_value=None),
            patch.object(web_search, "configured", return_value=True),
            patch.object(web_search, "search", return_value=empty),
            patch.object(chat_service, "stream_completion", fake_stream),
        ):
            client = TestClient(app)
            response = client.post(
                "/api/v1/chat",
                json={"message": "look this up: obscure xyzzy page", "model": "auto"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn(web_search.EMPTY_TOAST, response.text)
        extra = captured.get("extra_system") or ""
        self.assertIn("no public hits", extra.lower())
        self.assertIn("answer from training", extra.lower())
        self.assertIn("web_search returned no public hits", extra.lower())


if __name__ == "__main__":
    unittest.main()
