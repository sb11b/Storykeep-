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
    ERROR_FORBIDDEN,
    ERROR_POST_DROPPED,
    ERROR_SIGN_IN,
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


class SharedClientSmokeTests(unittest.TestCase):
    def test_no_client_specific_routes(self):
        paths = {getattr(route, "path", "") for route in _app().routes}
        junior = [path for path in paths if "/junior" in path]
        self.assertTrue(junior)
        self.assertFalse(any(path.endswith("/phone") or "/phone/" in path for path in junior))
        self.assertFalse(any(path.endswith("/windows") or "/windows/" in path for path in junior))

    def test_phone_and_windows_require_login(self):
        client = TestClient(_app())
        sleeps: list[float] = []
        phone = phone_client(client, sleeper=sleeps.append)
        windows = windows_client(client, sleeper=sleeps.append)
        self.assertEqual(phone.post_turn("from the phone").status_code, 401)
        self.assertEqual(windows.post_turn("from the overlay").status_code, 401)
        self.assertEqual(phone.project().status_code, 401)
        self.assertEqual(windows.search("trailer").status_code, 401)
        self.assertEqual(phone.list_threads().status_code, 401)
        self.assertEqual(windows.list_messages().status_code, 401)

    def test_demo_is_forbidden_for_both_clients(self):
        demo = SimpleNamespace(id=uuid.uuid4(), email="steve@storykeep.local", is_demo_locked=True)
        client = TestClient(_app(demo))
        phone = phone_client(client, sleeper=lambda _: None)
        windows = windows_client(client, sleeper=lambda _: None)
        phone_post = phone.post_turn("no")
        self.assertEqual(phone_post.status_code, 403)
        self.assertEqual(phone_post.error, ERROR_FORBIDDEN)
        self.assertFalse(phone_post)
        self.assertEqual(phone.last_failed_post["payload"]["text"], "no")
        self.assertEqual(windows.open_thread("Overlay").status_code, 403)
        self.assertEqual(phone.list_threads().status_code, 403)
        self.assertEqual(windows.list_messages().error, ERROR_FORBIDDEN)

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

    def test_get_threads_and_messages_use_shared_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        thread = SimpleNamespace(
            id=thread_id,
            title="Shared",
            venue_last="phone",
            status="open",
            summary=None,
            created_at=now,
            updated_at=now,
        )
        message = SimpleNamespace(
            id=uuid.uuid4(),
            thread_id=thread_id,
            role="user",
            content="hello from the client",
            venue="phone",
            meta={},
            created_at=now,
        )
        app = _app(_owner())
        with (
            patch("app.routers.junior_shared.store.list_threads", return_value=[thread]),
            patch("app.routers.junior_shared.store.list_messages", return_value=[message]) as listed,
            patch("app.routers.junior_shared.store.last_open_thread", return_value=thread),
        ):
            http = TestClient(app)
            threads = phone_client(http, sleeper=lambda _: None).list_threads()
            by_id = windows_client(http, sleeper=lambda _: None).list_messages(thread_id)
            latest = phone_client(http, sleeper=lambda _: None).list_messages()
        self.assertEqual(threads.status_code, 200)
        self.assertEqual(threads.json()[0]["title"], "Shared")
        self.assertEqual(by_id.status_code, 200)
        self.assertEqual(by_id.json()[0]["content"], "hello from the client")
        self.assertEqual(latest.status_code, 200)
        self.assertEqual(listed.call_args.args[2], thread_id)

    def test_retries_401_then_succeeds_without_dropping_the_post(self):
        thread, user_msg = _turn("phone")
        app = _app(_owner())
        http = TestClient(app)
        real_post = http.post
        calls = {"n": 0}

        def flaky_post(path, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return SimpleNamespace(status_code=401, text="Not authenticated", json=lambda: {"detail": "Not authenticated"})
            return real_post(path, **kwargs)

        http.post = flaky_post
        sleeps: list[float] = []
        with patch(
            "app.routers.junior_shared.store.post_turn",
            return_value=(thread, user_msg, None, "stubbed_no_key"),
        ) as post_turn:
            client = phone_client(http, sleeper=sleeps.append)
            response = client.post_turn("retry me")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.error)
        self.assertTrue(response)
        self.assertEqual(calls["n"], 2)
        self.assertEqual(sleeps, [0.25])
        self.assertIsNone(client.last_failed_post)
        self.assertEqual(post_turn.call_args.kwargs["content"], "retry me")

    def test_retries_403_and_5xx_then_keeps_the_failed_post(self):
        statuses = [403, 500, 503]
        http = SimpleNamespace()

        def flaky_post(path, **kwargs):
            status = statuses.pop(0)
            return SimpleNamespace(status_code=status, text="fail", json=lambda: {"detail": "fail"})

        http.post = flaky_post
        sleeps: list[float] = []
        client = windows_client(http, sleeper=sleeps.append)
        response = client.post_turn("keep this")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.error, ERROR_POST_DROPPED)
        self.assertFalse(response)
        self.assertEqual(sleeps, [0.25, 0.5])
        self.assertEqual(client.last_error, ERROR_POST_DROPPED)
        self.assertEqual(client.last_failed_post["payload"]["text"], "keep this")
        self.assertEqual(client.last_failed_post["status_code"], 503)
        self.assertEqual(client.last_failed_post["attempts"], 3)

    def test_401_after_retries_is_a_visible_sign_in_error(self):
        http = SimpleNamespace(post=lambda path, **kwargs: SimpleNamespace(status_code=401, text="", json=lambda: {}))
        client = phone_client(http, sleeper=lambda _: None)
        response = client.post_turn("held")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.error, ERROR_SIGN_IN)
        self.assertEqual(client.last_failed_post["payload"]["text"], "held")


if __name__ == "__main__":
    unittest.main()
