"""Smoke: junior-phone and windows-overlay hit the shared Memory API, not new routes."""

from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.deps import get_current_user
from app.routers import junior_shared as shared_router
from app.services.junior_shared_clients import (
    MAX_ATTEMPTS,
    SharedMemoryError,
    phone_client,
    windows_client,
)


def _app(user=None):
    app = FastAPI()
    app.include_router(shared_router.router, prefix="/api/v1")
    if user is None:
        return app

    def fake_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _owner():
    return SimpleNamespace(id=uuid.uuid4(), email="angry.tune8751@fastmail.com", is_demo_locked=False)


def _turn(venue: str):
    now = datetime.now(timezone.utc)
    thread_id = uuid.uuid4()
    thread = SimpleNamespace(
        id=thread_id,
        title="Shared",
        venue_last=venue,
        status="open",
        summary=None,
        created_at=now,
        updated_at=now,
    )
    user_msg = SimpleNamespace(
        id=uuid.uuid4(),
        thread_id=thread_id,
        role="user",
        content="hello from the client",
        venue=venue,
        meta={},
        created_at=now,
    )
    return thread, user_msg


class _ScriptedHttp:
    def __init__(self, outcomes: list[int | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, str]] = []

    def _next(self, method: str, path: str) -> SimpleNamespace:
        self.calls.append((method, path))
        if not self.outcomes:
            raise AssertionError("unexpected extra HTTP call")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(status_code=outcome, json=lambda: {"ok": True})

    def get(self, path: str, **_kwargs) -> SimpleNamespace:
        return self._next("GET", path)

    def post(self, path: str, **_kwargs) -> SimpleNamespace:
        return self._next("POST", path)


class SharedClientSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._sleep = patch("app.services.junior_shared_clients._sleep")
        self._sleep.start()
        self.addCleanup(self._sleep.stop)

    def test_no_client_specific_routes(self):
        paths = {getattr(route, "path", "") for route in _app().routes}
        junior = [path for path in paths if "/junior" in path]
        self.assertTrue(junior)
        self.assertFalse(any(path.endswith("/phone") or "/phone/" in path for path in junior))
        self.assertFalse(any(path.endswith("/windows") or "/windows/" in path for path in junior))
        self.assertIn("/api/v1/junior/threads", junior)
        self.assertTrue(any("/threads/{thread_id}/messages" in path for path in junior))

    def test_phone_and_windows_require_login(self):
        client = TestClient(_app())
        with self.assertRaises(SharedMemoryError) as phone_post:
            phone_client(client).post_turn("from the phone")
        self.assertEqual(phone_post.exception.status_code, 401)
        self.assertEqual(phone_post.exception.attempts, MAX_ATTEMPTS)
        self.assertIn("Sign in required", phone_post.exception.user_message)
        self.assertIn("did not save this message", phone_post.exception.user_message)

        with self.assertRaises(SharedMemoryError) as windows_post:
            windows_client(client).post_turn("from the overlay")
        self.assertEqual(windows_post.exception.status_code, 401)

        with self.assertRaises(SharedMemoryError) as project:
            phone_client(client).project()
        self.assertEqual(project.exception.status_code, 401)

        with self.assertRaises(SharedMemoryError) as search:
            windows_client(client).search("trailer")
        self.assertEqual(search.exception.status_code, 401)

        with self.assertRaises(SharedMemoryError) as threads:
            phone_client(client).get_threads()
        self.assertEqual(threads.exception.status_code, 401)
        self.assertIn("did not load threads", threads.exception.user_message)

        with self.assertRaises(SharedMemoryError) as messages:
            windows_client(client).get_messages(uuid.uuid4())
        self.assertEqual(messages.exception.status_code, 401)
        self.assertIn("did not load messages", messages.exception.user_message)

    def test_demo_is_forbidden_for_both_clients(self):
        demo = SimpleNamespace(id=uuid.uuid4(), email="steve@storykeep.local", is_demo_locked=True)
        client = TestClient(_app(demo))
        with self.assertRaises(SharedMemoryError) as phone_post:
            phone_client(client).post_turn("no")
        self.assertEqual(phone_post.exception.status_code, 403)
        self.assertEqual(phone_post.exception.attempts, MAX_ATTEMPTS)
        self.assertIn("cannot use Junior shared memory", phone_post.exception.user_message)
        self.assertIn("did not save this message", phone_post.exception.user_message)

        with self.assertRaises(SharedMemoryError) as overlay:
            windows_client(client).open_thread("Overlay")
        self.assertEqual(overlay.exception.status_code, 403)

        with self.assertRaises(SharedMemoryError) as threads:
            phone_client(client).get_threads()
        self.assertEqual(threads.exception.status_code, 403)

        with self.assertRaises(SharedMemoryError) as messages:
            windows_client(client).get_messages(uuid.uuid4())
        self.assertEqual(messages.exception.status_code, 403)

    def test_phone_posts_on_the_shared_messages_route(self):
        thread, user_msg = _turn("phone")
        app = _app(_owner())
        with patch(
            "app.routers.junior_shared.store.post_turn",
            return_value=(thread, user_msg, None, "stubbed_no_key"),
        ) as post_turn:
            response = phone_client(TestClient(app)).post_turn("from the phone")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_message"]["venue"], "phone")
        self.assertEqual(post_turn.call_args.kwargs["venue"], "phone")
        self.assertEqual(post_turn.call_args.kwargs["device_label"], "junior-mobile")
        self.assertEqual(post_turn.call_args.kwargs["content"], "from the phone")

    def test_windows_posts_on_the_same_route_with_its_venue(self):
        thread, user_msg = _turn("windows")
        app = _app(_owner())
        with patch(
            "app.routers.junior_shared.store.post_turn",
            return_value=(thread, user_msg, None, "stubbed_no_key"),
        ) as post_turn:
            response = windows_client(TestClient(app)).post_turn("from the overlay", thread_id=thread.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_message"]["venue"], "windows")
        self.assertEqual(post_turn.call_args.kwargs["venue"], "windows")
        self.assertEqual(post_turn.call_args.kwargs["device_label"], "windows-overlay")
        self.assertEqual(post_turn.call_args.kwargs["thread_id"], thread.id)

    def test_phone_project_slug_is_junior_phone(self):
        client = phone_client(object())
        self.assertEqual(client.project_slug, "junior-phone")
        self.assertEqual(client.venue, "phone")
        self.assertEqual(windows_client(object()).project_slug, "windows-overlay")
        self.assertEqual(windows_client(object()).venue, "windows")

    def test_clients_get_threads_and_messages_on_shared_routes(self):
        thread, user_msg = _turn("phone")
        app = _app(_owner())
        with patch("app.routers.junior_shared.store.list_threads", return_value=[thread]) as listed:
            phone_rows = phone_client(TestClient(app)).get_threads()
        self.assertEqual(phone_rows.status_code, 200)
        self.assertEqual(phone_rows.json()[0]["venue_last"], "phone")
        listed.assert_called_once()

        with patch("app.routers.junior_shared.store.list_messages", return_value=[user_msg]) as messages:
            overlay_rows = windows_client(TestClient(app)).get_messages(thread.id)
        self.assertEqual(overlay_rows.status_code, 200)
        self.assertEqual(overlay_rows.json()[0]["venue"], "phone")
        self.assertEqual(messages.call_args.args[2], thread.id)

    def test_retry_then_succeed_does_not_drop_a_post(self):
        http = _ScriptedHttp([503, 401, 200])
        with patch("app.services.junior_shared_clients._sleep") as slept:
            response = phone_client(http).post_turn("keep this")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(http.calls), 3)
        self.assertTrue(all(path.endswith("/messages") for _, path in http.calls))
        self.assertEqual(slept.call_count, 2)
        self.assertEqual([call.args[0] for call in slept.call_args_list], [0.2, 0.5])

    def test_retry_exhausted_on_403_surfaces_a_clear_error(self):
        http = _ScriptedHttp([403, 403, 403])
        with patch("app.services.junior_shared_clients._sleep") as slept:
            with self.assertRaises(SharedMemoryError) as ctx:
                windows_client(http).post_turn("must not vanish")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.attempts, 3)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertEqual(len(http.calls), 3)
        self.assertEqual(slept.call_count, 2)

    def test_retry_exhausted_on_5xx_does_not_drop_the_post(self):
        http = _ScriptedHttp([500, 502, 503])
        with self.assertRaises(SharedMemoryError) as ctx:
            phone_client(http).post_turn("still here")
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("server error", ctx.exception.user_message)
        self.assertIn("did not save this message", ctx.exception.user_message)
        self.assertEqual(len(http.calls), 3)

    def test_transport_error_retries_then_explains(self):
        http = _ScriptedHttp([ConnectionError("reset"), ConnectionError("reset"), ConnectionError("reset")])
        with self.assertRaises(SharedMemoryError) as ctx:
            windows_client(http).open_thread("Overlay")
        self.assertIsNone(ctx.exception.status_code)
        self.assertIn("could not reach the server", ctx.exception.user_message)
        self.assertEqual(len(http.calls), 3)

    def test_get_retries_then_returns_threads(self):
        http = _ScriptedHttp([503, 200])
        response = phone_client(http).get_threads()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(http.calls, [("GET", "/api/v1/junior/threads"), ("GET", "/api/v1/junior/threads")])


if __name__ == "__main__":
    unittest.main()
