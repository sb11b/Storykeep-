"""Smoke: junior-phone and windows-overlay hit the shared Memory API, not new routes."""

from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.deps import get_current_user
from app.routers import junior_shared as shared_router
from app.services.junior_shared_clients import (
    HEALTH_STAMP,
    MAX_ATTEMPTS,
    LocalPostQueue,
    SharedMemoryError,
    next_page_cursor,
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
        self.params: list[dict] = []

    def _next(self, method: str, path: str, **kwargs) -> SimpleNamespace:
        self.calls.append((method, path))
        self.params.append(kwargs.get("params") or {})
        if not self.outcomes:
            raise AssertionError("unexpected extra HTTP call")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        headers = {"X-Next-Cursor": "page-2"} if outcome == 200 and kwargs.get("params") else {}
        return SimpleNamespace(status_code=outcome, json=lambda: {"ok": True}, headers=headers)

    def get(self, path: str, **kwargs) -> SimpleNamespace:
        return self._next("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> SimpleNamespace:
        return self._next("POST", path, **kwargs)


def _queue_path() -> Path:
    return Path(tempfile.mkdtemp()) / "last_failed_post.json"


def _phone(http):
    return phone_client(http, queue_path=_queue_path())


def _windows(http):
    return windows_client(http, queue_path=_queue_path())


class SharedClientSmokeTests(unittest.TestCase):
    def test_health_stamp_is_agents_page_v1(self):
        self.assertEqual(HEALTH_STAMP, "junior-client-agents-page-v1")
        build = json.loads(
            (Path(__file__).resolve().parents[1] / "app" / "build-info.json").read_text(encoding="utf-8")
        )
        self.assertEqual(build["sha"], HEALTH_STAMP)
        main_src = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")
        self.assertIn("HEALTH_STAMP", main_src)
        self.assertIn("junior_clients", main_src)

    def test_no_client_specific_routes(self):
        paths = {getattr(route, "path", "") for route in _app().routes}
        junior = [path for path in paths if "/junior" in path]
        self.assertTrue(junior)
        self.assertFalse(any(path.endswith("/phone") or "/phone/" in path for path in junior))
        self.assertFalse(any(path.endswith("/windows") or "/windows/" in path for path in junior))
        self.assertIn("/api/v1/junior/threads", junior)
        self.assertIn("/api/v1/junior/messages", junior)
        self.assertIn("/api/v1/junior/agents", junior)
        self.assertTrue(any("/threads/{thread_id}/messages" in path for path in junior))

    def test_phone_and_windows_require_login(self):
        client = TestClient(_app())
        with self.assertRaises(SharedMemoryError) as phone_post:
            _phone(client).post_turn("from the phone")
        self.assertEqual(phone_post.exception.status_code, 401)
        self.assertEqual(phone_post.exception.attempts, MAX_ATTEMPTS)
        self.assertIn("Sign in required", phone_post.exception.user_message)
        self.assertIn("did not save this message", phone_post.exception.user_message)

        with self.assertRaises(SharedMemoryError) as windows_post:
            _windows(client).post_turn("from the overlay")
        self.assertEqual(windows_post.exception.status_code, 401)

        with self.assertRaises(SharedMemoryError) as project:
            _phone(client).project()
        self.assertEqual(project.exception.status_code, 401)

        with self.assertRaises(SharedMemoryError) as search:
            _windows(client).search("trailer")
        self.assertEqual(search.exception.status_code, 401)

        with self.assertRaises(SharedMemoryError) as threads:
            _phone(client).get_threads()
        self.assertEqual(threads.exception.status_code, 401)
        self.assertIn("did not load threads", threads.exception.user_message)

        with self.assertRaises(SharedMemoryError) as messages:
            _windows(client).get_messages(uuid.uuid4())
        self.assertEqual(messages.exception.status_code, 401)
        self.assertIn("did not load messages", messages.exception.user_message)

        with self.assertRaises(SharedMemoryError) as recent:
            _phone(client).get_recent_messages()
        self.assertEqual(recent.exception.status_code, 401)

    def test_demo_is_forbidden_for_both_clients(self):
        demo = SimpleNamespace(id=uuid.uuid4(), email="steve@storykeep.local", is_demo_locked=True)
        client = TestClient(_app(demo))
        with self.assertRaises(SharedMemoryError) as phone_post:
            _phone(client).post_turn("no")
        self.assertEqual(phone_post.exception.status_code, 403)
        self.assertEqual(phone_post.exception.attempts, MAX_ATTEMPTS)
        self.assertIn("cannot use Junior shared memory", phone_post.exception.user_message)
        self.assertIn("did not save this message", phone_post.exception.user_message)

        with self.assertRaises(SharedMemoryError) as overlay:
            _windows(client).open_thread("Overlay")
        self.assertEqual(overlay.exception.status_code, 403)

        with self.assertRaises(SharedMemoryError) as threads:
            _phone(client).get_threads()
        self.assertEqual(threads.exception.status_code, 403)

        with self.assertRaises(SharedMemoryError) as messages:
            _windows(client).get_messages(uuid.uuid4())
        self.assertEqual(messages.exception.status_code, 403)

        with self.assertRaises(SharedMemoryError) as recent:
            _phone(client).get_recent_messages(limit=5)
        self.assertEqual(recent.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", recent.exception.user_message)

    def test_phone_posts_on_the_shared_messages_route(self):
        thread, user_msg = _turn("phone")
        app = _app(_owner())
        with patch(
            "app.routers.junior_shared.store.post_turn",
            return_value=(thread, user_msg, None, "stubbed_no_key"),
        ) as post_turn:
            response = _phone(TestClient(app)).post_turn("from the phone")
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
            response = _windows(TestClient(app)).post_turn("from the overlay", thread_id=thread.id)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_message"]["venue"], "windows")
        self.assertEqual(post_turn.call_args.kwargs["venue"], "windows")
        self.assertEqual(post_turn.call_args.kwargs["device_label"], "windows-overlay")
        self.assertEqual(post_turn.call_args.kwargs["thread_id"], thread.id)

    def test_phone_project_slug_is_junior_phone(self):
        client = _phone(object())
        self.assertEqual(client.project_slug, "junior-phone")
        self.assertEqual(client.venue, "phone")
        self.assertEqual(_windows(object()).project_slug, "windows-overlay")
        self.assertEqual(_windows(object()).venue, "windows")

    def test_clients_get_threads_and_messages_on_shared_routes(self):
        thread, user_msg = _turn("phone")
        app = _app(_owner())
        with patch(
            "app.routers.junior_shared.store.list_threads_page",
            return_value=([thread], None),
        ) as listed:
            phone_rows = _phone(TestClient(app)).get_threads()
        self.assertEqual(phone_rows.status_code, 200)
        self.assertEqual(phone_rows.json()[0]["venue_last"], "phone")
        listed.assert_called_once()

        with patch(
            "app.routers.junior_shared.store.list_messages_page",
            return_value=([user_msg], None),
        ) as messages:
            overlay_rows = _windows(TestClient(app)).get_messages(thread.id)
        self.assertEqual(overlay_rows.status_code, 200)
        self.assertEqual(overlay_rows.json()[0]["venue"], "phone")
        self.assertEqual(messages.call_args.args[2], thread.id)

        with patch(
            "app.routers.junior_shared.store.list_recent_messages_page",
            return_value=([user_msg], str(user_msg.id)),
        ) as recent:
            listed_recent = _phone(TestClient(app)).get_recent_messages(limit=1, before_id=user_msg.id)
        self.assertEqual(listed_recent.status_code, 200)
        self.assertEqual(listed_recent.headers.get("x-next-cursor"), str(user_msg.id))
        self.assertEqual(recent.call_args.kwargs["limit"], 1)

    def test_retry_then_succeed_does_not_drop_a_post(self):
        http = _ScriptedHttp([503, 401, 200])
        with patch("app.services.junior_shared_clients._sleep") as slept:
            response = _phone(http).post_turn("keep this")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(http.calls), 3)
        self.assertTrue(all(path.endswith("/messages") for _, path in http.calls))
        self.assertEqual(slept.call_count, 2)
        self.assertEqual([call.args[0] for call in slept.call_args_list], [0.2, 0.5])

    def test_retry_exhausted_on_403_surfaces_a_clear_error(self):
        http = _ScriptedHttp([403, 403, 403])
        with patch("app.services.junior_shared_clients._sleep") as slept:
            with self.assertRaises(SharedMemoryError) as ctx:
                overlay = _windows(http)
                overlay.post_turn("must not vanish")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.attempts, 3)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertEqual(overlay.user_visible_error, ctx.exception.user_message)
        self.assertIn("must not vanish", overlay.last_failed_post["text"])
        self.assertEqual(overlay.surface_status()["user_visible_error"], ctx.exception.user_message)
        self.assertEqual(len(http.calls), 3)
        self.assertEqual(slept.call_count, 2)

    def test_retry_exhausted_on_5xx_does_not_drop_the_post(self):
        http = _ScriptedHttp([500, 502, 503])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                phone = _phone(http)
                phone.post_turn("still here")
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("server error", ctx.exception.user_message)
        self.assertIn("did not save this message", ctx.exception.user_message)
        self.assertEqual(phone.user_visible_error, ctx.exception.user_message)
        self.assertEqual(phone.last_failed_post["text"], "still here")
        self.assertEqual(len(http.calls), 3)

    def test_transport_error_retries_then_explains(self):
        http = _ScriptedHttp([ConnectionError("reset"), ConnectionError("reset"), ConnectionError("reset")])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _windows(http).open_thread("Overlay")
        self.assertIsNone(ctx.exception.status_code)
        self.assertIn("could not reach the server", ctx.exception.user_message)
        self.assertEqual(len(http.calls), 3)

    def test_get_retries_then_returns_threads(self):
        http = _ScriptedHttp([503, 200])
        with patch("app.services.junior_shared_clients._sleep"):
            response = _phone(http).get_threads()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(http.calls, [("GET", "/api/v1/junior/threads"), ("GET", "/api/v1/junior/threads")])

    def test_failed_post_survives_restart_and_replays_after_login(self):
        path = _queue_path()
        http = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError):
                phone_client(http, queue_path=path).post_turn("keep after restart")
        self.assertTrue(path.is_file())

        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["text"], "keep after restart")
        self.assertIn("server error", restarted.user_visible_error)
        self.assertEqual(restarted.surface_status()["venue"], "phone")

        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(replayed.last_failed_post)
        self.assertIsNone(replayed.user_visible_error)
        self.assertFalse(path.exists())
        self.assertEqual(replay_http.calls, [("POST", "/api/v1/junior/messages")])

    def test_queue_does_not_replay_under_a_different_auth(self):
        path = _queue_path()
        http = _ScriptedHttp([403, 403, 403])
        client = windows_client(http, queue_path=path)
        client.mark_authenticated("owner-a")
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError):
                client.post_turn("belongs to A")
        self.assertEqual(client.last_failed_post["auth_key"], "owner-a")

        other_http = _ScriptedHttp([200])
        other = windows_client(other_http, queue_path=path)
        replayed = other.replay_after_login("owner-b")
        self.assertIsNone(replayed)
        self.assertEqual(other.last_failed_post["text"], "belongs to A")
        self.assertIn("different sign-in", other.user_visible_error)
        self.assertEqual(other_http.calls, [])

    def test_paginated_gets_pass_limit_and_cursor(self):
        http = _ScriptedHttp([200, 200, 200])
        phone = _phone(http)
        first = phone.get_threads(limit=2, cursor="thread-1")
        self.assertEqual(http.params[0], {"limit": 2, "cursor": "thread-1"})
        self.assertEqual(next_page_cursor(first), "page-2")

        overlay = _windows(http)
        thread_id = uuid.uuid4()
        overlay.get_messages(thread_id, limit=3, before_id=thread_id)
        self.assertEqual(http.params[1]["limit"], 3)
        self.assertEqual(http.params[1]["before_id"], str(thread_id))

        phone.get_recent_messages(limit=4, cursor="msg-9")
        self.assertEqual(http.calls[2], ("GET", "/api/v1/junior/messages"))
        self.assertEqual(http.params[2], {"limit": 4, "cursor": "msg-9"})

    def test_search_and_memories_pass_page_params(self):
        http = _ScriptedHttp([200, 200, 403, 403, 403])
        phone = _phone(http)
        phone.search("trailer", limit=2, cursor="msg-1")
        self.assertEqual(http.calls[0], ("GET", "/api/v1/junior/search"))
        self.assertEqual(http.params[0], {"q": "trailer", "limit": 2, "cursor": "msg-1"})

        overlay = _windows(http)
        overlay.get_memories(kind="note", limit=3, before_id="mem-9")
        self.assertEqual(http.calls[1], ("GET", "/api/v1/junior/memories"))
        self.assertEqual(http.params[1]["limit"], 3)
        self.assertEqual(http.params[1]["kind"], "note")

        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _phone(http).search("blocked")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)

    def test_continue_posts_on_shared_resume_route(self):
        thread, user_msg = _turn("phone")
        app = _app(_owner())
        with patch(
            "app.routers.junior_shared.store.thread_owned",
            return_value=thread,
        ), patch(
            "app.routers.junior_shared.store.post_turn",
            return_value=(thread, user_msg, None, "stubbed_no_key"),
        ), patch(
            "app.routers.junior_shared.store.list_messages",
            return_value=[user_msg],
        ):
            response = _phone(TestClient(app)).continue_thread(thread.id, text="from the phone")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_message"]["venue"], "phone")

        http = _ScriptedHttp([403, 403, 403])
        overlay = _windows(http)
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                overlay.continue_thread(thread.id, text="must stay queued")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(overlay.last_failed_post["text"], "must stay queued")
        self.assertEqual(overlay.last_failed_post["kind"], "continue")
        self.assertIn("/continue", overlay.last_failed_post["path"])
        self.assertEqual(overlay.surface_status()["queue_depth"], 1)

    def test_fifo_queue_keeps_two_failed_posts_and_replays_in_order(self):
        path = _queue_path()
        first = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError):
                phone_client(first, queue_path=path).post_turn("first keep")
        second = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError):
                phone_client(second, queue_path=path).post_turn("second keep")

        restarted = phone_client(object(), queue_path=path)
        self.assertEqual([post["text"] for post in restarted.failed_posts], ["first keep", "second keep"])
        self.assertEqual(restarted.last_failed_post["text"], "first keep")
        self.assertEqual(restarted.surface_status()["queue_depth"], 2)

        replay_http = _ScriptedHttp([200, 200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            replay_http.calls,
            [("POST", "/api/v1/junior/messages"), ("POST", "/api/v1/junior/messages")],
        )
        self.assertEqual([call[1] for call in replay_http.calls], ["/api/v1/junior/messages"] * 2)
        self.assertFalse(path.exists())
        self.assertEqual(replayed.failed_posts, [])

    def test_both_clients_surface_queue_errors_not_only_logs(self):
        path_phone = _queue_path()
        path_windows = _queue_path()
        LocalPostQueue(path_phone).save(
            {
                "text": "from the phone",
                "user_message": "Sign in required. Junior did not save this message.",
                "venue": "phone",
            }
        )
        LocalPostQueue(path_windows).save(
            {
                "text": "from the overlay",
                "user_message": "This account cannot use Junior shared memory. Junior did not save this message.",
                "venue": "windows",
            }
        )
        phone = phone_client(object(), queue_path=path_phone)
        overlay = windows_client(object(), queue_path=path_windows)
        self.assertIn("Sign in required", phone.surface_status()["user_visible_error"])
        self.assertIn("cannot use Junior shared memory", overlay.surface_status()["user_visible_error"])
        self.assertEqual(phone.surface_status()["last_failed_post"]["text"], "from the phone")
        self.assertEqual(overlay.surface_status()["last_failed_post"]["text"], "from the overlay")

    def test_continue_replay_uses_continue_route(self):
        path = _queue_path()
        thread_id = uuid.uuid4()
        http = _ScriptedHttp([403, 403, 403])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError):
                phone_client(http, queue_path=path).continue_thread(thread_id, text="resume this")
        self.assertTrue(path.is_file())

        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            replay_http.calls,
            [("POST", f"/api/v1/junior/threads/{thread_id}/continue")],
        )
        self.assertFalse(path.exists())

    def test_projects_and_agent_context_pass_params(self):
        http = _ScriptedHttp([200, 200, 403, 403, 403])
        phone = _phone(http)
        phone.get_projects(limit=2, cursor="proj-1")
        self.assertEqual(http.calls[0], ("GET", "/api/v1/junior/projects"))
        self.assertEqual(http.params[0], {"limit": 2, "cursor": "proj-1"})

        overlay = _windows(http)
        thread_id = uuid.uuid4()
        overlay.get_agent_context("storykeep", q="finance", thread_id=thread_id)
        self.assertEqual(http.calls[1], ("GET", "/api/v1/junior/agent-context"))
        self.assertEqual(http.params[1]["project"], "storykeep")
        self.assertEqual(http.params[1]["q"], "finance")
        self.assertEqual(http.params[1]["thread_id"], str(thread_id))

        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _phone(http).get_agent_context()
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertIn("did not load agent context", ctx.exception.user_message)

    def test_project_and_agent_writes_queue_and_replay(self):
        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500, 500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as project_err:
                phone_client(fail, queue_path=path).upsert_project(
                    "storykeep",
                    display_name="StoryKeep",
                    kind="app",
                )
        self.assertEqual(project_err.exception.status_code, 500)
        self.assertIn("did not save this project", project_err.exception.user_message)
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as agent_err:
                phone_client(fail, queue_path=path).launch_agent(
                    "Fix the memory API",
                    project_slug="storykeep",
                )
        self.assertEqual(agent_err.exception.status_code, 500)
        self.assertIn("did not record this agent launch", agent_err.exception.user_message)

        restarted = phone_client(object(), queue_path=path)
        self.assertEqual([post["kind"] for post in restarted.failed_posts], ["project", "agent"])
        self.assertEqual(restarted.last_failed_post["slug"], "storykeep")
        self.assertEqual(restarted.failed_posts[1]["prompt"], "Fix the memory API")

        replay_http = _ScriptedHttp([200, 200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            replay_http.calls,
            [
                ("POST", "/api/v1/junior/projects"),
                ("POST", "/api/v1/junior/agents"),
            ],
        )
        self.assertFalse(path.exists())

    def test_agent_runs_pass_page_params_and_403(self):
        http = _ScriptedHttp([200, 403, 403, 403])
        overlay = _windows(http)
        overlay.get_agent_runs(limit=2, cursor="run-1", project="storykeep")
        self.assertEqual(http.calls[0], ("GET", "/api/v1/junior/agents"))
        self.assertEqual(http.params[0], {"limit": 2, "cursor": "run-1", "project": "storykeep"})

        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _phone(http).get_agent_runs()
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertIn("did not load agent runs", ctx.exception.user_message)


if __name__ == "__main__":
    unittest.main()
