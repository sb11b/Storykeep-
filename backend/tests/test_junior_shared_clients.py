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
        self.json_bodies: list[dict] = []

    def _next(self, method: str, path: str, **kwargs) -> SimpleNamespace:
        self.calls.append((method, path))
        self.params.append(kwargs.get("params") or {})
        self.json_bodies.append(kwargs.get("json") or {})
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
    def test_health_stamp_matches_build(self):
        self.assertEqual(HEALTH_STAMP, "junior-client-thread-context-get-v1")
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
        self.assertIn("/api/v1/junior/sessions", junior)
        self.assertTrue(any(path.endswith("/threads/{thread_id}") for path in junior))
        self.assertTrue(any("/threads/{thread_id}/messages" in path for path in junior))
        self.assertTrue(any(path.endswith("/memories/{memory_id}") for path in junior))
        self.assertTrue(any(path.endswith("/projects/{slug}") for path in junior))
        self.assertTrue(any(path.endswith("/agents/{run_id}") for path in junior))
        self.assertTrue(any(path.endswith("/sessions/{session_id}") for path in junior))
        self.assertTrue(any(path.endswith("/messages/{message_id}") for path in junior))
        self.assertTrue(any(path.endswith("/search/{message_id}") for path in junior))
        self.assertTrue(any(path.endswith("/agent-context/{slug}") for path in junior))
        self.assertTrue(any(path.endswith("/threads/{thread_id}/messages/{message_id}") for path in junior))
        self.assertTrue(any(path.endswith("/threads/{thread_id}/continue") for path in junior))
        self.assertTrue(any(path.endswith("/threads/{thread_id}/memories/{memory_id}") for path in junior))
        self.assertTrue(any(path.endswith("/threads/{thread_id}/agents/{run_id}") for path in junior))
        self.assertTrue(any(path.endswith("/threads/{thread_id}/agents") for path in junior))
        self.assertTrue(any(path.endswith("/threads/{thread_id}/search/{message_id}") for path in junior))
        self.assertTrue(any(path.endswith("/threads/{thread_id}/search") for path in junior))
        self.assertTrue(
            any(path.endswith("/threads/{thread_id}/agent-context/{slug}") for path in junior)
        )
        self.assertTrue(any(path.endswith("/projects/{slug}/search") for path in junior))

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

        with self.assertRaises(SharedMemoryError) as one_thread:
            _windows(client).get_thread(uuid.uuid4())
        self.assertEqual(one_thread.exception.status_code, 401)
        self.assertIn("did not load this thread", one_thread.exception.user_message)

        with self.assertRaises(SharedMemoryError) as one_memory:
            _windows(client).get_memory(uuid.uuid4())
        self.assertEqual(one_memory.exception.status_code, 401)
        self.assertIn("did not load this memory", one_memory.exception.user_message)

        with self.assertRaises(SharedMemoryError) as one_run:
            _phone(client).get_agent_run(uuid.uuid4())
        self.assertEqual(one_run.exception.status_code, 401)
        self.assertIn("did not load this agent run", one_run.exception.user_message)

        with self.assertRaises(SharedMemoryError) as one_session:
            _windows(client).get_session(uuid.uuid4())
        self.assertEqual(one_session.exception.status_code, 401)
        self.assertIn("did not load this session", one_session.exception.user_message)

        with self.assertRaises(SharedMemoryError) as one_message:
            _phone(client).get_message(uuid.uuid4())
        self.assertEqual(one_message.exception.status_code, 401)
        self.assertIn("did not load this message", one_message.exception.user_message)

        with self.assertRaises(SharedMemoryError) as one_project:
            _windows(client).get_project("storykeep")
        self.assertEqual(one_project.exception.status_code, 401)
        self.assertIn("did not load this project", one_project.exception.user_message)

        with self.assertRaises(SharedMemoryError) as one_hit:
            _phone(client).get_search_hit(uuid.uuid4())
        self.assertEqual(one_hit.exception.status_code, 401)
        self.assertIn("did not load this search hit", one_hit.exception.user_message)

        with self.assertRaises(SharedMemoryError) as one_ctx:
            _windows(client).get_agent_context("storykeep")
        self.assertEqual(one_ctx.exception.status_code, 401)
        self.assertIn("did not load this agent context", one_ctx.exception.user_message)

        with self.assertRaises(SharedMemoryError) as nested:
            _phone(client).get_thread_message(uuid.uuid4(), uuid.uuid4())
        self.assertEqual(nested.exception.status_code, 401)
        self.assertIn("did not load this message", nested.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_message_updated:
            _windows(client).update_thread_message(uuid.uuid4(), uuid.uuid4(), "revised turn")
        self.assertEqual(thread_message_updated.exception.status_code, 401)
        self.assertIn("did not update this thread message", thread_message_updated.exception.user_message)

        with self.assertRaises(SharedMemoryError) as continue_page:
            _phone(client).get_continue(uuid.uuid4())
        self.assertEqual(continue_page.exception.status_code, 401)
        self.assertIn("did not load this continue", continue_page.exception.user_message)

        with self.assertRaises(SharedMemoryError) as project_agent:
            _windows(client).get_project_agent(uuid.uuid4(), "storykeep")
        self.assertEqual(project_agent.exception.status_code, 401)
        self.assertIn("did not load this project agent", project_agent.exception.user_message)

        with self.assertRaises(SharedMemoryError) as project_agents:
            _phone(client).get_project_agents("storykeep")
        self.assertEqual(project_agents.exception.status_code, 401)
        self.assertIn("did not load these project agents", project_agents.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_memory:
            _phone(client).get_thread_memory(uuid.uuid4(), uuid.uuid4())
        self.assertEqual(thread_memory.exception.status_code, 401)
        self.assertIn("did not load this thread memory", thread_memory.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_memories:
            _windows(client).get_thread_memories(uuid.uuid4())
        self.assertEqual(thread_memories.exception.status_code, 401)
        self.assertIn("did not load these thread memories", thread_memories.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_agent:
            _phone(client).get_thread_agent(uuid.uuid4(), uuid.uuid4())
        self.assertEqual(thread_agent.exception.status_code, 401)
        self.assertIn("did not load this thread agent", thread_agent.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_agents:
            _windows(client).get_thread_agents(uuid.uuid4())
        self.assertEqual(thread_agents.exception.status_code, 401)
        self.assertIn("did not load these thread agents", thread_agents.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_search:
            _phone(client).get_thread_search_hit(uuid.uuid4(), uuid.uuid4())
        self.assertEqual(thread_search.exception.status_code, 401)
        self.assertIn("did not load this thread search hit", thread_search.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_search_page:
            _windows(client).get_thread_search(uuid.uuid4(), "notes")
        self.assertEqual(thread_search_page.exception.status_code, 401)
        self.assertIn("did not load these thread search hits", thread_search_page.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_context:
            _phone(client).get_thread_agent_context(uuid.uuid4(), "storykeep")
        self.assertEqual(thread_context.exception.status_code, 401)
        self.assertIn("did not load this thread context", thread_context.exception.user_message)

        with self.assertRaises(SharedMemoryError) as project_search_page:
            _phone(client).get_project_search("storykeep", "notes")
        self.assertEqual(project_search_page.exception.status_code, 401)
        self.assertIn("did not load these project search hits", project_search_page.exception.user_message)

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
        self.assertIn("did not open this thread", overlay.exception.user_message)

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

        with self.assertRaises(SharedMemoryError) as one_thread:
            _windows(client).get_thread(uuid.uuid4())
        self.assertEqual(one_thread.exception.status_code, 403)
        self.assertIn("did not load this thread", one_thread.exception.user_message)

        with self.assertRaises(SharedMemoryError) as one_memory:
            _windows(client).get_memory(uuid.uuid4())
        self.assertEqual(one_memory.exception.status_code, 403)
        self.assertIn("did not load this memory", one_memory.exception.user_message)

        with self.assertRaises(SharedMemoryError) as updated:
            _phone(client).update_thread(uuid.uuid4(), status="archived")
        self.assertEqual(updated.exception.status_code, 403)
        self.assertIn("did not update this thread", updated.exception.user_message)

        with self.assertRaises(SharedMemoryError) as one_run:
            _phone(client).get_agent_run(uuid.uuid4())
        self.assertEqual(one_run.exception.status_code, 403)
        self.assertIn("did not load this agent run", one_run.exception.user_message)

        with self.assertRaises(SharedMemoryError) as project_updated:
            _windows(client).update_project("storykeep", display_name="StoryKeep")
        self.assertEqual(project_updated.exception.status_code, 403)
        self.assertIn("did not update this project", project_updated.exception.user_message)

        with self.assertRaises(SharedMemoryError) as memory_updated:
            _phone(client).update_memory(uuid.uuid4(), "revised fact")
        self.assertEqual(memory_updated.exception.status_code, 403)
        self.assertIn("did not update this memory", memory_updated.exception.user_message)

        with self.assertRaises(SharedMemoryError) as one_session:
            _windows(client).get_session(uuid.uuid4())
        self.assertEqual(one_session.exception.status_code, 403)
        self.assertIn("did not load this session", one_session.exception.user_message)

        with self.assertRaises(SharedMemoryError) as one_message:
            _phone(client).get_message(uuid.uuid4())
        self.assertEqual(one_message.exception.status_code, 403)
        self.assertIn("did not load this message", one_message.exception.user_message)

        with self.assertRaises(SharedMemoryError) as session_updated:
            _windows(client).update_session(uuid.uuid4(), device_label="phone-2")
        self.assertEqual(session_updated.exception.status_code, 403)
        self.assertIn("did not update this session", session_updated.exception.user_message)

        with self.assertRaises(SharedMemoryError) as message_updated:
            _phone(client).update_message(uuid.uuid4(), "revised turn")
        self.assertEqual(message_updated.exception.status_code, 403)
        self.assertIn("did not update this message", message_updated.exception.user_message)

        with self.assertRaises(SharedMemoryError) as one_project:
            _windows(client).get_project("storykeep")
        self.assertEqual(one_project.exception.status_code, 403)
        self.assertIn("did not load this project", one_project.exception.user_message)

        with self.assertRaises(SharedMemoryError) as agent_updated:
            _phone(client).update_agent(uuid.uuid4(), status="launched")
        self.assertEqual(agent_updated.exception.status_code, 403)
        self.assertIn("did not update this agent run", agent_updated.exception.user_message)

        with self.assertRaises(SharedMemoryError) as one_hit:
            _windows(client).get_search_hit(uuid.uuid4())
        self.assertEqual(one_hit.exception.status_code, 403)
        self.assertIn("did not load this search hit", one_hit.exception.user_message)

        with self.assertRaises(SharedMemoryError) as search_updated:
            _phone(client).update_search_hit(uuid.uuid4(), snippet="pinned snippet")
        self.assertEqual(search_updated.exception.status_code, 403)
        self.assertIn("did not update this search hit", search_updated.exception.user_message)

        with self.assertRaises(SharedMemoryError) as one_ctx:
            _windows(client).get_agent_context("storykeep")
        self.assertEqual(one_ctx.exception.status_code, 403)
        self.assertIn("did not load this agent context", one_ctx.exception.user_message)

        with self.assertRaises(SharedMemoryError) as context_updated:
            _phone(client).update_agent_context("storykeep", q="finance")
        self.assertEqual(context_updated.exception.status_code, 403)
        self.assertIn("did not update this agent context", context_updated.exception.user_message)

        with self.assertRaises(SharedMemoryError) as nested:
            _windows(client).get_thread_message(uuid.uuid4(), uuid.uuid4())
        self.assertEqual(nested.exception.status_code, 403)
        self.assertIn("did not load this message", nested.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_message_updated:
            _phone(client).update_thread_message(uuid.uuid4(), uuid.uuid4(), "revised turn")
        self.assertEqual(thread_message_updated.exception.status_code, 403)
        self.assertIn("did not update this thread message", thread_message_updated.exception.user_message)

        with self.assertRaises(SharedMemoryError) as continue_page:
            _windows(client).get_continue(uuid.uuid4())
        self.assertEqual(continue_page.exception.status_code, 403)
        self.assertIn("did not load this continue", continue_page.exception.user_message)

        with self.assertRaises(SharedMemoryError) as project_agent:
            _phone(client).get_project_agent(uuid.uuid4(), "storykeep")
        self.assertEqual(project_agent.exception.status_code, 403)
        self.assertIn("did not load this project agent", project_agent.exception.user_message)

        with self.assertRaises(SharedMemoryError) as project_agent_updated:
            _windows(client).update_project_agent(uuid.uuid4(), status="launched")
        self.assertEqual(project_agent_updated.exception.status_code, 403)
        self.assertIn("did not update this project agent", project_agent_updated.exception.user_message)

        with self.assertRaises(SharedMemoryError) as project_agents:
            _phone(client).get_project_agents("storykeep")
        self.assertEqual(project_agents.exception.status_code, 403)
        self.assertIn("did not load these project agents", project_agents.exception.user_message)

        with self.assertRaises(SharedMemoryError) as project_agent_launched:
            _windows(client).launch_project_agent("Fix the memory API", slug="storykeep")
        self.assertEqual(project_agent_launched.exception.status_code, 403)
        self.assertIn("did not record this project agent", project_agent_launched.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_memory:
            _phone(client).get_thread_memory(uuid.uuid4(), uuid.uuid4())
        self.assertEqual(thread_memory.exception.status_code, 403)
        self.assertIn("did not load this thread memory", thread_memory.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_memory_updated:
            _windows(client).update_thread_memory(uuid.uuid4(), uuid.uuid4(), "revised fact")
        self.assertEqual(thread_memory_updated.exception.status_code, 403)
        self.assertIn("did not update this thread memory", thread_memory_updated.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_memories:
            _phone(client).get_thread_memories(uuid.uuid4())
        self.assertEqual(thread_memories.exception.status_code, 403)
        self.assertIn("did not load these thread memories", thread_memories.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_agent:
            _windows(client).get_thread_agent(uuid.uuid4(), uuid.uuid4())
        self.assertEqual(thread_agent.exception.status_code, 403)
        self.assertIn("did not load this thread agent", thread_agent.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_agent_updated:
            _phone(client).update_thread_agent(uuid.uuid4(), uuid.uuid4(), status="launched")
        self.assertEqual(thread_agent_updated.exception.status_code, 403)
        self.assertIn("did not update this thread agent", thread_agent_updated.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_agents:
            _windows(client).get_thread_agents(uuid.uuid4())
        self.assertEqual(thread_agents.exception.status_code, 403)
        self.assertIn("did not load these thread agents", thread_agents.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_agent_launched:
            _phone(client).launch_thread_agent("Fix the memory API", uuid.uuid4(), project_slug="storykeep")
        self.assertEqual(thread_agent_launched.exception.status_code, 403)
        self.assertIn("did not record this thread agent", thread_agent_launched.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_search:
            _windows(client).get_thread_search_hit(uuid.uuid4(), uuid.uuid4())
        self.assertEqual(thread_search.exception.status_code, 403)
        self.assertIn("did not load this thread search hit", thread_search.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_search_updated:
            _phone(client).update_thread_search_hit(uuid.uuid4(), uuid.uuid4(), snippet="pinned")
        self.assertEqual(thread_search_updated.exception.status_code, 403)
        self.assertIn("did not update this thread search hit", thread_search_updated.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_search_page:
            _windows(client).get_thread_search(uuid.uuid4(), "notes")
        self.assertEqual(thread_search_page.exception.status_code, 403)
        self.assertIn("did not load these thread search hits", thread_search_page.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_searched:
            _phone(client).search_thread(uuid.uuid4(), "notes")
        self.assertEqual(thread_searched.exception.status_code, 403)
        self.assertIn("did not run this thread search", thread_searched.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_context:
            _windows(client).get_thread_agent_context(uuid.uuid4(), "storykeep")
        self.assertEqual(thread_context.exception.status_code, 403)
        self.assertIn("did not load this thread context", thread_context.exception.user_message)

        with self.assertRaises(SharedMemoryError) as thread_context_updated:
            _phone(client).update_thread_agent_context(uuid.uuid4(), "storykeep", q="finance")
        self.assertEqual(thread_context_updated.exception.status_code, 403)
        self.assertIn("did not update this thread context", thread_context_updated.exception.user_message)

        with self.assertRaises(SharedMemoryError) as project_search_page:
            _windows(client).get_project_search("storykeep", "notes")
        self.assertEqual(project_search_page.exception.status_code, 403)
        self.assertIn("did not load these project search hits", project_search_page.exception.user_message)

        with self.assertRaises(SharedMemoryError) as project_searched:
            _phone(client).search_project("storykeep", "notes")
        self.assertEqual(project_searched.exception.status_code, 403)
        self.assertIn("did not run this project search", project_searched.exception.user_message)

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
            "app.routers.junior_shared.store.list_messages_page",
            return_value=([user_msg], None),
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

    def test_memory_writes_queue_and_replay(self):
        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                phone_client(fail, queue_path=path).upsert_memory(
                    "Prefers short replies",
                    kind="preference",
                )
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("did not save this memory", ctx.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "memory")
        self.assertEqual(restarted.last_failed_post["content"], "Prefers short replies")

        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(replay_http.calls, [("POST", "/api/v1/junior/memories")])
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
        self.assertEqual(http.calls[1], ("GET", "/api/v1/junior/agent-context/storykeep"))
        self.assertEqual(http.params[1]["q"], "finance")
        self.assertEqual(http.params[1]["thread_id"], str(thread_id))

        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _phone(http).get_agent_context()
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertIn("did not load this agent context", ctx.exception.user_message)

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

    def test_continue_passes_page_params_and_403(self):
        http = _ScriptedHttp([200, 403, 403, 403])
        thread_id = uuid.uuid4()
        overlay = _windows(http)
        overlay.continue_thread(thread_id, text="page this", limit=2, cursor="msg-1")
        self.assertEqual(http.calls[0], ("POST", f"/api/v1/junior/threads/{thread_id}/continue"))
        self.assertEqual(http.params[0], {"limit": 2, "cursor": "msg-1"})

        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _phone(http).upsert_memory("blocked")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertIn("did not save this memory", ctx.exception.user_message)

    def test_sessions_pass_page_params_and_403(self):
        http = _ScriptedHttp([200, 403, 403, 403])
        overlay = _windows(http)
        overlay.get_sessions(limit=2, cursor="sess-1", venue="windows")
        self.assertEqual(http.calls[0], ("GET", "/api/v1/junior/sessions"))
        self.assertEqual(http.params[0], {"limit": 2, "cursor": "sess-1", "venue": "windows"})

        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _phone(http).get_sessions()
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertIn("did not load sessions", ctx.exception.user_message)

    def test_session_heartbeat_queues_and_replays(self):
        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                phone_client(fail, queue_path=path).touch_session()
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("did not record this session", ctx.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "session")
        self.assertEqual(restarted.last_failed_post["venue"], "phone")
        self.assertEqual(restarted.last_failed_post["device_label"], "junior-mobile")

        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(replay_http.calls, [("POST", "/api/v1/junior/sessions")])
        self.assertFalse(path.exists())

    def test_get_thread_403(self):
        http = _ScriptedHttp([403, 403, 403])
        thread_id = uuid.uuid4()
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _phone(http).get_thread(thread_id)
        self.assertEqual(http.calls[0], ("GET", f"/api/v1/junior/threads/{thread_id}"))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertIn("did not load this thread", ctx.exception.user_message)

    def test_open_thread_queues_and_replays(self):
        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                phone_client(fail, queue_path=path).open_thread("Phone chat", text="first turn")
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("did not open this thread", ctx.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "thread")
        self.assertEqual(restarted.last_failed_post["title"], "Phone chat")
        self.assertEqual(restarted.last_failed_post["text"], "first turn")

        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(replay_http.calls, [("POST", "/api/v1/junior/threads")])
        self.assertFalse(path.exists())

    def test_get_memory_403(self):
        http = _ScriptedHttp([403, 403, 403])
        memory_id = uuid.uuid4()
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _phone(http).get_memory(memory_id)
        self.assertEqual(http.calls[0], ("GET", f"/api/v1/junior/memories/{memory_id}"))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertIn("did not load this memory", ctx.exception.user_message)

    def test_thread_update_queues_and_replays(self):
        path = _queue_path()
        thread_id = uuid.uuid4()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                phone_client(fail, queue_path=path).update_thread(
                    thread_id,
                    title="Closed chat",
                    status="archived",
                )
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("did not update this thread", ctx.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "thread_update")
        self.assertEqual(restarted.last_failed_post["title"], "Closed chat")
        self.assertEqual(restarted.last_failed_post["status"], "archived")
        self.assertEqual(restarted.last_failed_post["thread_id"], str(thread_id))

        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(replay_http.calls, [("POST", f"/api/v1/junior/threads/{thread_id}")])
        self.assertFalse(path.exists())

    def test_get_agent_run_403(self):
        http = _ScriptedHttp([403, 403, 403])
        run_id = uuid.uuid4()
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _phone(http).get_agent_run(run_id)
        self.assertEqual(http.calls[0], ("GET", f"/api/v1/junior/agents/{run_id}"))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertIn("did not load this agent run", ctx.exception.user_message)

    def test_project_update_queues_and_replays(self):
        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                phone_client(fail, queue_path=path).update_project(
                    "junior-phone",
                    display_name="Junior mobile",
                    notes="Expo client",
                )
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("did not update this project", ctx.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "project_update")
        self.assertEqual(restarted.last_failed_post["slug"], "junior-phone")
        self.assertEqual(restarted.last_failed_post["display_name"], "Junior mobile")
        self.assertEqual(restarted.last_failed_post["notes"], "Expo client")

        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(replay_http.calls, [("POST", "/api/v1/junior/projects/junior-phone")])
        self.assertFalse(path.exists())

    def test_get_session_403(self):
        http = _ScriptedHttp([403, 403, 403])
        session_id = uuid.uuid4()
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _phone(http).get_session(session_id)
        self.assertEqual(http.calls[0], ("GET", f"/api/v1/junior/sessions/{session_id}"))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertIn("did not load this session", ctx.exception.user_message)

    def test_memory_update_queues_and_replays(self):
        path = _queue_path()
        memory_id = uuid.uuid4()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                phone_client(fail, queue_path=path).update_memory(
                    memory_id,
                    "revised fact",
                    kind="note",
                )
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("did not update this memory", ctx.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "memory_update")
        self.assertEqual(restarted.last_failed_post["content"], "revised fact")
        self.assertEqual(restarted.last_failed_post["memory_kind"], "note")
        self.assertEqual(restarted.last_failed_post["id"], str(memory_id))

        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(replay_http.calls, [("POST", f"/api/v1/junior/memories/{memory_id}")])
        self.assertFalse(path.exists())

    def test_get_message_403(self):
        http = _ScriptedHttp([403, 403, 403])
        message_id = uuid.uuid4()
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _phone(http).get_message(message_id)
        self.assertEqual(http.calls[0], ("GET", f"/api/v1/junior/messages/{message_id}"))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertIn("did not load this message", ctx.exception.user_message)

    def test_session_update_queues_and_replays(self):
        path = _queue_path()
        session_id = uuid.uuid4()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                phone_client(fail, queue_path=path).update_session(
                    session_id,
                    device_label="junior-mobile-2",
                )
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("did not update this session", ctx.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "session_update")
        self.assertEqual(restarted.last_failed_post["device_label"], "junior-mobile-2")
        self.assertEqual(restarted.last_failed_post["session_id"], str(session_id))

        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(replay_http.calls, [("POST", f"/api/v1/junior/sessions/{session_id}")])
        self.assertFalse(path.exists())

    def test_get_project_403(self):
        http = _ScriptedHttp([403, 403, 403])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _phone(http).get_project("storykeep")
        self.assertEqual(http.calls[0], ("GET", "/api/v1/junior/projects/storykeep"))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertIn("did not load this project", ctx.exception.user_message)

    def test_message_update_queues_and_replays(self):
        path = _queue_path()
        message_id = uuid.uuid4()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                phone_client(fail, queue_path=path).update_message(
                    message_id,
                    "revised turn",
                    venue="phone",
                )
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("did not update this message", ctx.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "message_update")
        self.assertEqual(restarted.last_failed_post["content"], "revised turn")
        self.assertEqual(restarted.last_failed_post["id"], str(message_id))

        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(replay_http.calls, [("POST", f"/api/v1/junior/messages/{message_id}")])
        self.assertFalse(path.exists())

    def test_get_search_hit_403(self):
        http = _ScriptedHttp([403, 403, 403])
        message_id = uuid.uuid4()
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _phone(http).get_search_hit(message_id)
        self.assertEqual(http.calls[0], ("GET", f"/api/v1/junior/search/{message_id}"))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertIn("did not load this search hit", ctx.exception.user_message)

    def test_agent_update_queues_and_replays(self):
        path = _queue_path()
        run_id = uuid.uuid4()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                phone_client(fail, queue_path=path).update_agent(
                    run_id,
                    prompt="keep going",
                    status="launched",
                )
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("did not update this agent run", ctx.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "agent_update")
        self.assertEqual(restarted.last_failed_post["prompt"], "keep going")
        self.assertEqual(restarted.last_failed_post["status"], "launched")
        self.assertEqual(restarted.last_failed_post["id"], str(run_id))

        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(replay_http.calls, [("POST", f"/api/v1/junior/agents/{run_id}")])
        self.assertFalse(path.exists())

    def test_get_agent_context_slug_403(self):
        http = _ScriptedHttp([403, 403, 403])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _phone(http).get_agent_context("storykeep")
        self.assertEqual(http.calls[0], ("GET", "/api/v1/junior/agent-context/storykeep"))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertIn("did not load this agent context", ctx.exception.user_message)

    def test_search_update_queues_and_replays(self):
        path = _queue_path()
        message_id = uuid.uuid4()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                phone_client(fail, queue_path=path).update_search_hit(
                    message_id,
                    snippet="pinned snippet",
                )
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("did not update this search hit", ctx.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "search_update")
        self.assertEqual(restarted.last_failed_post["snippet"], "pinned snippet")
        self.assertEqual(restarted.last_failed_post["message_id"], str(message_id))

        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(replay_http.calls, [("POST", f"/api/v1/junior/search/{message_id}")])
        self.assertFalse(path.exists())

    def test_get_thread_message_403(self):
        http = _ScriptedHttp([403, 403, 403])
        thread_id = uuid.uuid4()
        message_id = uuid.uuid4()
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _phone(http).get_thread_message(thread_id, message_id)
        self.assertEqual(
            http.calls[0],
            ("GET", f"/api/v1/junior/threads/{thread_id}/messages/{message_id}"),
        )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertIn("did not load this message", ctx.exception.user_message)

    def test_agent_context_update_queues_and_replays(self):
        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                phone_client(fail, queue_path=path).update_agent_context("storykeep", q="finance")
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("did not update this agent context", ctx.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "context_update")
        self.assertEqual(restarted.last_failed_post["q"], "finance")
        self.assertEqual(restarted.last_failed_post["slug"], "storykeep")

        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(replay_http.calls, [("POST", "/api/v1/junior/agent-context/storykeep")])
        self.assertFalse(path.exists())

    def test_get_continue_403(self):
        http = _ScriptedHttp([200, 403, 403, 403])
        thread_id = uuid.uuid4()
        _phone(http).get_continue(thread_id, limit=2, cursor="abc")
        self.assertEqual(http.calls[0], ("GET", f"/api/v1/junior/threads/{thread_id}/continue"))
        self.assertEqual(http.params[0], {"limit": 2, "cursor": "abc"})
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _windows(http).get_continue(thread_id)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("cannot use Junior shared memory", ctx.exception.user_message)
        self.assertIn("did not load this continue", ctx.exception.user_message)

    def test_thread_message_update_queues_and_replays(self):
        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500])
        thread_id = uuid.uuid4()
        message_id = uuid.uuid4()
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                phone_client(fail, queue_path=path).update_thread_message(
                    thread_id, message_id, "revised turn"
                )
        self.assertEqual(ctx.exception.status_code, 500)
        self.assertIn("did not update this thread message", ctx.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "thread_message_update")
        self.assertEqual(restarted.last_failed_post["content"], "revised turn")
        self.assertEqual(restarted.last_failed_post["thread_id"], str(thread_id))
        self.assertEqual(restarted.last_failed_post["message_id"], str(message_id))

        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            replay_http.calls,
            [("POST", f"/api/v1/junior/threads/{thread_id}/messages/{message_id}")],
        )
        self.assertFalse(path.exists())

    def test_project_agent_get_403_and_update_replays(self):
        run_id = uuid.uuid4()
        http = _ScriptedHttp([403, 403, 403])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _phone(http).get_project_agent(run_id, "storykeep")
        self.assertEqual(http.calls[0], ("GET", f"/api/v1/junior/projects/storykeep/agents/{run_id}"))
        self.assertEqual(ctx.exception.status_code, 403)

        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as updated:
                phone_client(fail, queue_path=path).update_project_agent(
                    run_id, slug="storykeep", status="launched", prompt="Keep going"
                )
        self.assertIn("did not update this project agent", updated.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "project_agent_update")
        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            replay_http.calls,
            [("POST", f"/api/v1/junior/projects/storykeep/agents/{run_id}")],
        )
        self.assertFalse(path.exists())

    def test_project_agents_page_403_and_launch_replays(self):
        http = _ScriptedHttp([200, 403, 403, 403])
        page = _phone(http).get_project_agents("storykeep", limit=2, cursor="abc")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(http.calls[0], ("GET", "/api/v1/junior/projects/storykeep/agents"))
        self.assertEqual(http.params[0], {"limit": 2, "cursor": "abc"})
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _windows(http).get_project_agents("storykeep")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("did not load these project agents", ctx.exception.user_message)

        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as launched:
                phone_client(fail, queue_path=path).launch_project_agent(
                    "Fix the memory API", slug="storykeep"
                )
        self.assertIn("did not record this project agent", launched.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "project_agent")
        self.assertEqual(restarted.last_failed_post["prompt"], "Fix the memory API")
        self.assertEqual(restarted.last_failed_post["slug"], "storykeep")
        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(replay_http.calls, [("POST", "/api/v1/junior/projects/storykeep/agents")])
        self.assertEqual(replay_http.json_bodies[0]["prompt"], "Fix the memory API")
        self.assertNotIn("project_slug", replay_http.json_bodies[0])
        self.assertFalse(path.exists())

    def test_thread_memory_get_403_and_update_replays(self):
        thread_id = uuid.uuid4()
        memory_id = uuid.uuid4()
        http = _ScriptedHttp([403, 403, 403])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _windows(http).get_thread_memory(thread_id, memory_id)
        self.assertEqual(
            http.calls[0],
            ("GET", f"/api/v1/junior/threads/{thread_id}/memories/{memory_id}"),
        )
        self.assertEqual(ctx.exception.status_code, 403)

        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as updated:
                phone_client(fail, queue_path=path).update_thread_memory(
                    thread_id, memory_id, "revised fact", kind="note"
                )
        self.assertIn("did not update this thread memory", updated.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "thread_memory_update")
        self.assertEqual(restarted.last_failed_post["content"], "revised fact")
        self.assertEqual(restarted.last_failed_post["thread_id"], str(thread_id))
        self.assertEqual(restarted.last_failed_post["memory_id"], str(memory_id))
        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            replay_http.calls,
            [("POST", f"/api/v1/junior/threads/{thread_id}/memories/{memory_id}")],
        )
        self.assertNotIn(
            ("POST", f"/api/v1/junior/memories/{memory_id}"),
            replay_http.calls,
        )
        self.assertFalse(path.exists())

    def test_thread_memories_page_403_and_create_replays(self):
        thread_id = uuid.uuid4()
        http = _ScriptedHttp([200, 403, 403, 403])
        page = _phone(http).get_thread_memories(thread_id, limit=2, cursor="abc")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(http.calls[0], ("GET", f"/api/v1/junior/threads/{thread_id}/memories"))
        self.assertEqual(http.params[0], {"limit": 2, "cursor": "abc"})
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _windows(http).get_thread_memories(thread_id)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("did not load these thread memories", ctx.exception.user_message)

        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as created:
                phone_client(fail, queue_path=path).create_thread_memory(
                    thread_id, "Prefers short replies", kind="note"
                )
        self.assertIn("did not save this thread memory", created.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "thread_memory")
        self.assertEqual(restarted.last_failed_post["content"], "Prefers short replies")
        self.assertEqual(restarted.last_failed_post["thread_id"], str(thread_id))
        self.assertEqual(restarted.last_failed_post["memory_kind"], "note")
        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            replay_http.calls,
            [("POST", f"/api/v1/junior/threads/{thread_id}/memories")],
        )
        self.assertEqual(replay_http.json_bodies[0]["content"], "Prefers short replies")
        self.assertEqual(replay_http.json_bodies[0]["kind"], "note")
        self.assertNotIn(("POST", "/api/v1/junior/memories"), replay_http.calls)
        self.assertFalse(path.exists())

    def test_thread_agent_get_403_and_update_replays(self):
        thread_id = uuid.uuid4()
        run_id = uuid.uuid4()
        http = _ScriptedHttp([403, 403, 403])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _windows(http).get_thread_agent(thread_id, run_id)
        self.assertEqual(
            http.calls[0],
            ("GET", f"/api/v1/junior/threads/{thread_id}/agents/{run_id}"),
        )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("did not load this thread agent", ctx.exception.user_message)

        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as updated:
                phone_client(fail, queue_path=path).update_thread_agent(
                    thread_id, run_id, status="launched", prompt="Keep going"
                )
        self.assertIn("did not update this thread agent", updated.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "thread_agent_update")
        self.assertEqual(restarted.last_failed_post["prompt"], "Keep going")
        self.assertEqual(restarted.last_failed_post["status"], "launched")
        self.assertEqual(restarted.last_failed_post["thread_id"], str(thread_id))
        self.assertEqual(restarted.last_failed_post["run_id"], str(run_id))
        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            replay_http.calls,
            [("POST", f"/api/v1/junior/threads/{thread_id}/agents/{run_id}")],
        )
        self.assertNotIn(("POST", f"/api/v1/junior/agents/{run_id}"), replay_http.calls)
        self.assertFalse(any("/projects/" in call[1] for call in replay_http.calls))
        self.assertFalse(path.exists())

    def test_thread_agents_page_403_and_launch_replays(self):
        thread_id = uuid.uuid4()
        http = _ScriptedHttp([200, 403, 403, 403])
        page = _phone(http).get_thread_agents(thread_id, limit=2, cursor="abc")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(http.calls[0], ("GET", f"/api/v1/junior/threads/{thread_id}/agents"))
        self.assertEqual(http.params[0], {"limit": 2, "cursor": "abc"})
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _windows(http).get_thread_agents(thread_id)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("did not load these thread agents", ctx.exception.user_message)

        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as launched:
                phone_client(fail, queue_path=path).launch_thread_agent(
                    "Fix the memory API", thread_id, project_slug="storykeep"
                )
        self.assertIn("did not record this thread agent", launched.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "thread_agent")
        self.assertEqual(restarted.last_failed_post["prompt"], "Fix the memory API")
        self.assertEqual(restarted.last_failed_post["thread_id"], str(thread_id))
        self.assertEqual(restarted.last_failed_post["project_slug"], "storykeep")
        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            replay_http.calls,
            [("POST", f"/api/v1/junior/threads/{thread_id}/agents")],
        )
        self.assertEqual(replay_http.json_bodies[0]["prompt"], "Fix the memory API")
        self.assertEqual(replay_http.json_bodies[0]["project_slug"], "storykeep")
        self.assertNotIn(("POST", "/api/v1/junior/agents"), replay_http.calls)
        self.assertNotIn(("POST", "/api/v1/junior/projects/storykeep/agents"), replay_http.calls)
        self.assertFalse(path.exists())

    def test_thread_search_get_403_and_update_replays(self):
        thread_id = uuid.uuid4()
        message_id = uuid.uuid4()
        http = _ScriptedHttp([403, 403, 403])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _windows(http).get_thread_search_hit(thread_id, message_id)
        self.assertEqual(
            http.calls[0],
            ("GET", f"/api/v1/junior/threads/{thread_id}/search/{message_id}"),
        )
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("did not load this thread search hit", ctx.exception.user_message)

        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as updated:
                phone_client(fail, queue_path=path).update_thread_search_hit(
                    thread_id, message_id, snippet="pinned snippet", venue="phone"
                )
        self.assertIn("did not update this thread search hit", updated.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "thread_search_update")
        self.assertEqual(restarted.last_failed_post["snippet"], "pinned snippet")
        self.assertEqual(restarted.last_failed_post["thread_id"], str(thread_id))
        self.assertEqual(restarted.last_failed_post["message_id"], str(message_id))
        self.assertEqual(restarted.last_failed_post["search_venue"], "phone")
        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            replay_http.calls,
            [("POST", f"/api/v1/junior/threads/{thread_id}/search/{message_id}")],
        )
        self.assertEqual(replay_http.json_bodies[0]["snippet"], "pinned snippet")
        self.assertEqual(replay_http.json_bodies[0]["venue"], "phone")
        self.assertNotIn(("POST", f"/api/v1/junior/search/{message_id}"), replay_http.calls)
        self.assertFalse(path.exists())

    def test_thread_search_page_403_and_replay(self):
        thread_id = uuid.uuid4()
        http = _ScriptedHttp([200, 403, 403, 403])
        page = _phone(http).get_thread_search(thread_id, "notes", limit=2, cursor="abc")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(http.calls[0], ("GET", f"/api/v1/junior/threads/{thread_id}/search"))
        self.assertEqual(http.params[0], {"limit": 2, "cursor": "abc", "q": "notes"})
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _windows(http).get_thread_search(thread_id, "notes")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("did not load these thread search hits", ctx.exception.user_message)

        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as searched:
                phone_client(fail, queue_path=path).search_thread(thread_id, "notes")
        self.assertIn("did not run this thread search", searched.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "thread_search")
        self.assertEqual(restarted.last_failed_post["q"], "notes")
        self.assertEqual(restarted.last_failed_post["thread_id"], str(thread_id))
        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            replay_http.calls,
            [("POST", f"/api/v1/junior/threads/{thread_id}/search")],
        )
        self.assertEqual(replay_http.json_bodies[0]["q"], "notes")
        self.assertNotIn(("GET", "/api/v1/junior/search"), replay_http.calls)
        self.assertFalse(any(call[1].endswith(f"/search/{thread_id}") for call in replay_http.calls))
        self.assertFalse(path.exists())

    def test_thread_context_get_403_and_update_replays(self):
        thread_id = uuid.uuid4()
        http = _ScriptedHttp([403, 403, 403])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _windows(http).get_thread_agent_context(thread_id, "storykeep", q="finance")
        self.assertEqual(
            http.calls[0],
            ("GET", f"/api/v1/junior/threads/{thread_id}/agent-context/storykeep"),
        )
        self.assertEqual(http.params[0], {"q": "finance"})
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("did not load this thread context", ctx.exception.user_message)

        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as updated:
                phone_client(fail, queue_path=path).update_thread_agent_context(
                    thread_id, "storykeep", q="finance"
                )
        self.assertIn("did not update this thread context", updated.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "thread_context_update")
        self.assertEqual(restarted.last_failed_post["q"], "finance")
        self.assertEqual(restarted.last_failed_post["slug"], "storykeep")
        self.assertEqual(restarted.last_failed_post["thread_id"], str(thread_id))
        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            replay_http.calls,
            [("POST", f"/api/v1/junior/threads/{thread_id}/agent-context/storykeep")],
        )
        self.assertEqual(replay_http.json_bodies[0]["q"], "finance")
        self.assertNotIn(("POST", "/api/v1/junior/agent-context/storykeep"), replay_http.calls)
        self.assertFalse(path.exists())

    def test_project_search_page_403_and_replay(self):
        http = _ScriptedHttp([200, 403, 403, 403])
        page = _phone(http).get_project_search("storykeep", "notes", limit=2, cursor="abc")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(http.calls[0], ("GET", "/api/v1/junior/projects/storykeep/search"))
        self.assertEqual(http.params[0], {"limit": 2, "cursor": "abc", "q": "notes"})
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as ctx:
                _windows(http).get_project_search("storykeep", "notes")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("did not load these project search hits", ctx.exception.user_message)

        path = _queue_path()
        fail = _ScriptedHttp([500, 500, 500])
        with patch("app.services.junior_shared_clients._sleep"):
            with self.assertRaises(SharedMemoryError) as searched:
                phone_client(fail, queue_path=path).search_project("storykeep", "notes")
        self.assertIn("did not run this project search", searched.exception.user_message)
        restarted = phone_client(object(), queue_path=path)
        self.assertEqual(restarted.last_failed_post["kind"], "project_search")
        self.assertEqual(restarted.last_failed_post["q"], "notes")
        self.assertEqual(restarted.last_failed_post["slug"], "storykeep")
        replay_http = _ScriptedHttp([200])
        replayed = phone_client(replay_http, queue_path=path)
        response = replayed.replay_after_login("owner-session")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            replay_http.calls,
            [("POST", "/api/v1/junior/projects/storykeep/search")],
        )
        self.assertEqual(replay_http.json_bodies[0]["q"], "notes")
        self.assertNotIn(("GET", "/api/v1/junior/search"), replay_http.calls)
        self.assertNotIn(("POST", "/api/v1/junior/threads/storykeep/search"), replay_http.calls)
        self.assertFalse(path.exists())

        self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
