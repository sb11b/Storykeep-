from __future__ import annotations

import inspect
import re
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.database import get_db
from app.deps import get_current_user, require_user
from app.routers import junior_shared as shared_router
from app.services import junior_shared_memory as store

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
JUNIOR_SQL = (
    MIGRATIONS / "001_junior_memory.sql",
    MIGRATIONS / "002_junior_projects.sql",
)


def _sql_statements(raw: str) -> list[str]:
    statement: list[str] = []
    out: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        statement.append(line)
        if stripped.endswith(";"):
            sql = "\n".join(statement).strip()
            statement = []
            if sql:
                out.append(sql)
    return out


def _assert_idempotent_sql(test: unittest.TestCase, raw: str, path: Path) -> None:
    statements = _sql_statements(raw)
    test.assertGreater(len(statements), 0, path)
    for sql in statements:
        compact = re.sub(r"\s+", " ", sql).upper()
        test.assertFalse(compact.startswith("DROP "), f"{path}: {sql}")
        if compact.startswith("CREATE "):
            test.assertIn("IF NOT EXISTS", compact, f"{path}: {sql}")
        if "ADD COLUMN" in compact:
            test.assertIn("IF NOT EXISTS", compact, f"{path}: {sql}")


def _owner():
    return SimpleNamespace(id=uuid.uuid4(), email="stevebitsko@duck.com", is_demo_locked=False)


def _app(user=None):
    app = FastAPI()
    app.include_router(shared_router.router, prefix="/api/v1")
    owner = user or _owner()

    def fake_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_user] = lambda: owner
    return app


class JuniorSharedRouteTests(unittest.TestCase):
    def test_unauthenticated_401(self):
        app = FastAPI()
        app.include_router(shared_router.router, prefix="/api/v1")
        client = TestClient(app)
        for path in (
            "/api/v1/junior/threads",
            "/api/v1/junior/messages",
            "/api/v1/junior/search?q=hello",
            "/api/v1/junior/memories",
            "/api/v1/junior/projects",
            "/api/v1/junior/agent-context?project=storykeep",
            "/api/v1/junior/agents",
            "/api/v1/junior/sessions",
            f"/api/v1/junior/threads/{uuid.uuid4()}",
            f"/api/v1/junior/memories/{uuid.uuid4()}",
            f"/api/v1/junior/agents/{uuid.uuid4()}",
            f"/api/v1/junior/sessions/{uuid.uuid4()}",
            f"/api/v1/junior/threads/{uuid.uuid4()}/sessions/{uuid.uuid4()}",
            f"/api/v1/junior/threads/{uuid.uuid4()}/sessions",
            f"/api/v1/junior/projects/storykeep/threads/{uuid.uuid4()}/sessions/{uuid.uuid4()}",
            f"/api/v1/junior/projects/storykeep/threads/{uuid.uuid4()}/sessions",
            f"/api/v1/junior/messages/{uuid.uuid4()}",
            f"/api/v1/junior/search/{uuid.uuid4()}",
            "/api/v1/junior/agent-context/storykeep",
        ):
            response = client.get(path)
            self.assertEqual(response.status_code, 401, path)
        self.assertEqual(client.post("/api/v1/junior/messages", json={"text": "hi", "venue": "phone"}).status_code, 401)
        self.assertEqual(client.post("/api/v1/junior/agents", json={"project_slug": "storykeep", "prompt": "go"}).status_code, 401)
        self.assertEqual(
            client.post("/api/v1/junior/memories", json={"kind": "note", "content": "keep"}).status_code,
            401,
        )
        self.assertEqual(
            client.post("/api/v1/junior/sessions", json={"venue": "phone", "device_label": "junior-mobile"}).status_code,
            401,
        )
        self.assertEqual(
            client.post(f"/api/v1/junior/threads/{uuid.uuid4()}", json={"status": "archived"}).status_code,
            401,
        )
        self.assertEqual(
            client.post(
                "/api/v1/junior/projects/storykeep",
                json={"slug": "storykeep", "display_name": "StoryKeep"},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/junior/memories/{uuid.uuid4()}",
                json={"kind": "note", "content": "keep"},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/junior/sessions/{uuid.uuid4()}",
                json={"device_label": "junior-mobile-2"},
            ).status_code,
            401,
        )
        thread_for_session = uuid.uuid4()
        session_for_thread = uuid.uuid4()
        self.assertEqual(
            client.get(
                f"/api/v1/junior/threads/{thread_for_session}/sessions/{session_for_thread}"
            ).status_code,
            401,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/junior/threads/{thread_for_session}/sessions/{session_for_thread}",
                json={"device_label": "junior-mobile-2"},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.get(f"/api/v1/junior/threads/{thread_for_session}/sessions").status_code,
            401,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/junior/threads/{thread_for_session}/sessions",
                json={"venue": "phone", "device_label": "junior-mobile"},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/junior/projects/storykeep/threads/{thread_for_session}/sessions/{session_for_thread}",
                json={"device_label": "junior-mobile-2"},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.get(
                f"/api/v1/junior/projects/storykeep/threads/{thread_for_session}/sessions"
            ).status_code,
            401,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/junior/projects/storykeep/threads/{thread_for_session}/sessions",
                json={"venue": "phone", "device_label": "junior-mobile"},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/junior/messages/{uuid.uuid4()}",
                json={"text": "revised turn", "venue": "phone"},
            ).status_code,
            401,
        )
        self.assertEqual(client.get("/api/v1/junior/projects/storykeep").status_code, 401)
        self.assertEqual(
            client.post(
                f"/api/v1/junior/agents/{uuid.uuid4()}",
                json={"status": "launched"},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/junior/search/{uuid.uuid4()}",
                json={"snippet": "pinned snippet"},
            ).status_code,
            401,
        )
        self.assertEqual(client.get("/api/v1/junior/agent-context/storykeep").status_code, 401)
        self.assertEqual(
            client.post(
                "/api/v1/junior/agent-context/storykeep",
                json={"q": "finance"},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.get(
                f"/api/v1/junior/threads/{uuid.uuid4()}/messages/{uuid.uuid4()}"
            ).status_code,
            401,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/junior/threads/{uuid.uuid4()}/messages/{uuid.uuid4()}",
                json={"text": "revised turn"},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.get(f"/api/v1/junior/threads/{uuid.uuid4()}/continue").status_code,
            401,
        )
        self.assertEqual(client.get("/api/v1/junior/projects/storykeep/agents").status_code, 401)
        self.assertEqual(
            client.post(
                "/api/v1/junior/projects/storykeep/agents",
                json={"prompt": "Fix the memory API"},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.get("/api/v1/junior/projects/storykeep/search", params={"q": "notes"}).status_code,
            401,
        )
        self.assertEqual(
            client.post("/api/v1/junior/projects/storykeep/search", json={"q": "notes"}).status_code,
            401,
        )
        self.assertEqual(
            client.get(f"/api/v1/junior/projects/storykeep/search/{uuid.uuid4()}").status_code,
            401,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/junior/projects/storykeep/search/{uuid.uuid4()}",
                json={"snippet": "pinned snippet"},
            ).status_code,
            401,
        )
        self.assertEqual(client.get("/api/v1/junior/projects/storykeep/agent-context").status_code, 401)
        self.assertEqual(client.get("/api/v1/junior/projects/storykeep/memories").status_code, 401)
        self.assertEqual(
            client.post(
                "/api/v1/junior/projects/storykeep/memories",
                json={"content": "Prefers short replies", "kind": "note"},
            ).status_code,
            401,
        )
        self.assertEqual(client.get("/api/v1/junior/projects/storykeep/threads").status_code, 401)
        self.assertEqual(
            client.post(
                "/api/v1/junior/projects/storykeep/threads",
                json={"title": "Lab notes", "text": "Start here"},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.get(f"/api/v1/junior/projects/storykeep/messages/{uuid.uuid4()}").status_code,
            401,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/junior/projects/storykeep/messages/{uuid.uuid4()}",
                json={"text": "revised turn", "venue": "phone"},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.post(
                "/api/v1/junior/projects/storykeep/agent-context",
                json={"q": "finance"},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.get(f"/api/v1/junior/projects/storykeep/agents/{uuid.uuid4()}").status_code,
            401,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/junior/projects/storykeep/agents/{uuid.uuid4()}",
                json={"status": "launched"},
            ).status_code,
            401,
        )
        thread_for_agents = uuid.uuid4()
        self.assertEqual(
            client.get(f"/api/v1/junior/threads/{thread_for_agents}/agents/{uuid.uuid4()}").status_code,
            401,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/junior/threads/{thread_for_agents}/agents/{uuid.uuid4()}",
                json={"status": "launched"},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.get(f"/api/v1/junior/threads/{thread_for_agents}/agents").status_code,
            401,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/junior/threads/{thread_for_agents}/agents",
                json={"prompt": "Fix the memory API", "project_slug": "storykeep"},
            ).status_code,
            401,
        )
        self.assertEqual(
            client.get(
                f"/api/v1/junior/projects/storykeep/threads/{thread_for_agents}/agents/{uuid.uuid4()}"
            ).status_code,
            401,
        )
        self.assertEqual(
            client.post(
                f"/api/v1/junior/projects/storykeep/threads/{thread_for_agents}/agents/{uuid.uuid4()}",
                json={"status": "launched"},
            ).status_code,
            401,
        )

    def test_demo_gets_403(self):
        app = _app(SimpleNamespace(id=uuid.uuid4(), email="steve@storykeep.local", is_demo_locked=True))
        client = TestClient(app)
        for method, path in (
            ("GET", "/api/v1/junior/threads"),
            ("GET", "/api/v1/junior/messages"),
            ("GET", "/api/v1/junior/search?q=hello"),
            ("GET", "/api/v1/junior/memories"),
            ("GET", "/api/v1/junior/projects"),
            ("GET", "/api/v1/junior/agent-context?project=storykeep"),
            ("GET", "/api/v1/junior/agents"),
            ("GET", "/api/v1/junior/sessions"),
            ("GET", f"/api/v1/junior/threads/{uuid.uuid4()}"),
            ("GET", f"/api/v1/junior/memories/{uuid.uuid4()}"),
            ("GET", f"/api/v1/junior/agents/{uuid.uuid4()}"),
            ("GET", f"/api/v1/junior/sessions/{uuid.uuid4()}"),
            ("GET", f"/api/v1/junior/messages/{uuid.uuid4()}"),
            ("GET", "/api/v1/junior/projects/storykeep"),
            ("GET", f"/api/v1/junior/search/{uuid.uuid4()}"),
            ("GET", "/api/v1/junior/agent-context/storykeep"),
            ("POST", "/api/v1/junior/agent-context/storykeep"),
            ("GET", f"/api/v1/junior/threads/{uuid.uuid4()}/messages/{uuid.uuid4()}"),
            ("POST", f"/api/v1/junior/threads/{uuid.uuid4()}/messages/{uuid.uuid4()}"),
            ("GET", f"/api/v1/junior/threads/{uuid.uuid4()}/continue"),
            ("GET", "/api/v1/junior/projects/storykeep/agents"),
            ("POST", "/api/v1/junior/projects/storykeep/agents"),
            ("GET", f"/api/v1/junior/projects/storykeep/agents/{uuid.uuid4()}"),
            ("POST", f"/api/v1/junior/projects/storykeep/agents/{uuid.uuid4()}"),
            ("GET", f"/api/v1/junior/threads/{uuid.uuid4()}/agents/{uuid.uuid4()}"),
            ("POST", f"/api/v1/junior/threads/{uuid.uuid4()}/agents/{uuid.uuid4()}"),
            ("GET", f"/api/v1/junior/threads/{uuid.uuid4()}/agents"),
            ("POST", f"/api/v1/junior/threads/{uuid.uuid4()}/agents"),
            ("GET", f"/api/v1/junior/projects/storykeep/threads/{uuid.uuid4()}/agents/{uuid.uuid4()}"),
            ("POST", f"/api/v1/junior/projects/storykeep/threads/{uuid.uuid4()}/agents/{uuid.uuid4()}"),
            ("GET", f"/api/v1/junior/threads/{uuid.uuid4()}/memories/{uuid.uuid4()}"),
            ("POST", f"/api/v1/junior/threads/{uuid.uuid4()}/memories/{uuid.uuid4()}"),
            ("POST", f"/api/v1/junior/search/{uuid.uuid4()}"),
            ("POST", f"/api/v1/junior/threads/{uuid.uuid4()}"),
            ("POST", f"/api/v1/junior/sessions/{uuid.uuid4()}"),
            ("GET", f"/api/v1/junior/threads/{uuid.uuid4()}/sessions/{uuid.uuid4()}"),
            ("POST", f"/api/v1/junior/threads/{uuid.uuid4()}/sessions/{uuid.uuid4()}"),
            ("GET", f"/api/v1/junior/threads/{uuid.uuid4()}/sessions"),
            ("POST", f"/api/v1/junior/threads/{uuid.uuid4()}/sessions"),
            ("GET", f"/api/v1/junior/projects/storykeep/threads/{uuid.uuid4()}/sessions/{uuid.uuid4()}"),
            ("POST", f"/api/v1/junior/projects/storykeep/threads/{uuid.uuid4()}/sessions/{uuid.uuid4()}"),
            ("GET", f"/api/v1/junior/projects/storykeep/threads/{uuid.uuid4()}/sessions"),
            ("POST", f"/api/v1/junior/projects/storykeep/threads/{uuid.uuid4()}/sessions"),
            ("POST", f"/api/v1/junior/messages/{uuid.uuid4()}"),
            ("POST", f"/api/v1/junior/agents/{uuid.uuid4()}"),
            ("POST", "/api/v1/junior/messages"),
            ("POST", "/api/v1/junior/agents"),
            ("POST", "/api/v1/junior/memories"),
            ("POST", f"/api/v1/junior/memories/{uuid.uuid4()}"),
            ("POST", "/api/v1/junior/sessions"),
            ("POST", "/api/v1/junior/projects/storykeep"),
            ("GET", "/api/v1/junior/projects/storykeep/search?q=notes"),
            ("POST", "/api/v1/junior/projects/storykeep/search"),
            ("GET", f"/api/v1/junior/projects/storykeep/search/{uuid.uuid4()}"),
            ("POST", f"/api/v1/junior/projects/storykeep/search/{uuid.uuid4()}"),
            ("GET", "/api/v1/junior/projects/storykeep/agent-context"),
            ("POST", "/api/v1/junior/projects/storykeep/agent-context"),
            ("GET", "/api/v1/junior/projects/storykeep/memories"),
            ("POST", "/api/v1/junior/projects/storykeep/memories"),
            ("GET", f"/api/v1/junior/projects/storykeep/messages/{uuid.uuid4()}"),
            ("POST", f"/api/v1/junior/projects/storykeep/messages/{uuid.uuid4()}"),
            ("GET", "/api/v1/junior/projects/storykeep/messages"),
            ("POST", "/api/v1/junior/projects/storykeep/messages"),
            ("GET", "/api/v1/junior/projects/storykeep/threads"),
            ("POST", "/api/v1/junior/projects/storykeep/threads"),
            ("GET", f"/api/v1/junior/projects/storykeep/threads/{uuid.uuid4()}"),
            ("POST", f"/api/v1/junior/projects/storykeep/threads/{uuid.uuid4()}"),
            (
                "GET",
                f"/api/v1/junior/projects/storykeep/threads/{uuid.uuid4()}/memories/{uuid.uuid4()}",
            ),
            (
                "POST",
                f"/api/v1/junior/projects/storykeep/threads/{uuid.uuid4()}/memories/{uuid.uuid4()}",
            ),
            (
                "GET",
                f"/api/v1/junior/projects/storykeep/threads/{uuid.uuid4()}/memories",
            ),
            (
                "POST",
                f"/api/v1/junior/projects/storykeep/threads/{uuid.uuid4()}/memories",
            ),
        ):
            response = client.request(
                method,
                path,
                json={
                    "text": "hi",
                    "venue": "phone",
                    "project_slug": "storykeep",
                    "prompt": "go",
                    "content": "keep",
                    "q": "notes",
                },
            )
            self.assertEqual(response.status_code, 403, path)

    def test_shared_routes_use_require_user(self):
        for route in shared_router.router.routes:
            endpoint = getattr(route, "endpoint", None)
            if endpoint is None:
                continue
            params = inspect.signature(endpoint).parameters
            self.assertIn("user", params, route.path)
            default = params["user"].default
            self.assertIsNotNone(default)
            self.assertIs(getattr(default, "dependency", None), require_user, route.path)

    def test_list_threads(self):
        now = datetime.now(timezone.utc)
        thread = SimpleNamespace(
            id=uuid.uuid4(),
            title="Equipment finance",
            venue_last="phone",
            status="open",
            summary=None,
            created_at=now,
            updated_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.list_threads_page",
            return_value=([thread], None),
        ) as listed:
            response = TestClient(app).get(
                "/api/v1/junior/threads",
                params={"limit": 1, "before_id": str(thread.id)},
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["title"], "Equipment finance")
        self.assertEqual(body[0]["venue_last"], "phone")
        self.assertEqual(response.headers.get("x-has-more"), "false")
        listed.assert_called_once()
        self.assertEqual(listed.call_args.kwargs["limit"], 1)
        self.assertEqual(str(listed.call_args.kwargs["before_id"]), str(thread.id))

    def test_create_thread_and_post_message(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        thread = SimpleNamespace(
            id=thread_id,
            title="New chat",
            venue_last="storykeep",
            status="open",
            summary=None,
            created_at=now,
            updated_at=now,
        )
        user_msg = SimpleNamespace(
            id=uuid.uuid4(),
            thread_id=thread_id,
            role="user",
            content="Remember the trailer quote",
            venue="windows",
            meta={},
            created_at=now,
        )
        app = _app()
        with patch("app.routers.junior_shared.store.create_thread", return_value=thread):
            created = TestClient(app).post("/api/v1/junior/threads", json={"title": "New chat", "venue": "storykeep"})
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["id"], str(thread_id))

        with patch(
            "app.routers.junior_shared.store.post_turn",
            return_value=(thread, user_msg, None, "stubbed_no_key"),
        ):
            posted = TestClient(app).post(
                f"/api/v1/junior/threads/{thread_id}/messages",
                json={"text": "Remember the trailer quote", "venue": "windows"},
            )
        self.assertEqual(posted.status_code, 200)
        body = posted.json()
        self.assertEqual(body["thread_id"], str(thread_id))
        self.assertEqual(body["user_message"]["content"], "Remember the trailer quote")
        self.assertIsNone(body["junior_message"])
        self.assertEqual(body["reply_status"], "stubbed_no_key")
        self.assertIn("Postgres", body["detail"])

        with patch(
            "app.routers.junior_shared.store.post_turn",
            return_value=(thread, user_msg, None, "stubbed_no_key"),
        ):
            loose = TestClient(app).post(
                "/api/v1/junior/messages",
                json={"text": "Remember the trailer quote", "venue": "phone"},
            )
        self.assertEqual(loose.status_code, 200)
        self.assertEqual(loose.json()["thread_id"], str(thread_id))

        with patch("app.routers.junior_shared.store.thread_owned", return_value=thread), patch(
            "app.routers.junior_shared.store.list_messages_page",
            return_value=([user_msg], str(user_msg.id)),
        ) as history:
            resumed = TestClient(app).post(
                f"/api/v1/junior/threads/{thread_id}/continue",
                params={"limit": 1, "cursor": str(user_msg.id)},
                json={},
            )
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["thread"]["id"], str(thread_id))
        self.assertEqual(len(resumed.json()["messages"]), 1)
        self.assertEqual(resumed.headers.get("x-next-cursor"), str(user_msg.id))
        self.assertEqual(history.call_args.kwargs["limit"], 1)
        self.assertEqual(history.call_args.kwargs["cursor"], str(user_msg.id))

        with patch("app.routers.junior_shared.store.thread_owned", return_value=thread) as owned:
            one = TestClient(app).get(f"/api/v1/junior/threads/{thread_id}")
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["id"], str(thread_id))
        self.assertEqual(one.json()["title"], "New chat")
        self.assertEqual(str(owned.call_args.args[2]), str(thread_id))

        archived = SimpleNamespace(
            id=thread_id,
            title="Closed chat",
            venue_last="storykeep",
            status="archived",
            summary=None,
            created_at=now,
            updated_at=now,
        )
        with patch("app.routers.junior_shared.store.message_owned", return_value=user_msg) as one_msg:
            loaded = TestClient(app).get(f"/api/v1/junior/messages/{user_msg.id}")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json()["content"], "Remember the trailer quote")
        self.assertEqual(str(one_msg.call_args.args[2]), str(user_msg.id))

        with patch(
            "app.routers.junior_shared.store.thread_message_owned", return_value=user_msg
        ) as nested_msg:
            nested = TestClient(app).get(
                f"/api/v1/junior/threads/{thread_id}/messages/{user_msg.id}"
            )
        self.assertEqual(nested.status_code, 200)
        self.assertEqual(nested.json()["content"], "Remember the trailer quote")
        self.assertEqual(str(nested_msg.call_args.args[2]), str(thread_id))
        self.assertEqual(str(nested_msg.call_args.args[3]), str(user_msg.id))

        with patch("app.routers.junior_shared.store.thread_owned", return_value=thread), patch(
            "app.routers.junior_shared.store.list_messages_page",
            return_value=([user_msg], str(user_msg.id)),
        ) as continue_page:
            history = TestClient(app).get(
                f"/api/v1/junior/threads/{thread_id}/continue",
                params={"limit": 1, "cursor": str(user_msg.id)},
            )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["thread"]["id"], str(thread_id))
        self.assertEqual(len(history.json()["messages"]), 1)
        self.assertIsNone(history.json()["user_message"])
        self.assertEqual(history.headers.get("x-next-cursor"), str(user_msg.id))
        self.assertEqual(continue_page.call_args.kwargs["limit"], 1)
        self.assertEqual(continue_page.call_args.kwargs["cursor"], str(user_msg.id))

        revised = SimpleNamespace(
            id=user_msg.id,
            thread_id=user_msg.thread_id,
            role=user_msg.role,
            content="revised turn",
            venue="phone",
            meta={},
            created_at=user_msg.created_at,
        )
        with patch("app.routers.junior_shared.store.update_message", return_value=revised) as patched:
            changed = TestClient(app).post(
                f"/api/v1/junior/messages/{user_msg.id}",
                json={"text": "revised turn", "venue": "phone"},
            )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["content"], "revised turn")
        self.assertEqual(str(patched.call_args.args[2]), str(user_msg.id))
        self.assertEqual(patched.call_args.kwargs["content"], "revised turn")

        with patch(
            "app.routers.junior_shared.store.update_thread_message", return_value=revised
        ) as nested_update:
            nested_changed = TestClient(app).post(
                f"/api/v1/junior/threads/{thread_id}/messages/{user_msg.id}",
                json={"text": "revised turn", "venue": "phone"},
            )
        self.assertEqual(nested_changed.status_code, 200)
        self.assertEqual(nested_changed.json()["content"], "revised turn")
        self.assertEqual(str(nested_update.call_args.args[2]), str(thread_id))
        self.assertEqual(str(nested_update.call_args.args[3]), str(user_msg.id))
        self.assertEqual(nested_update.call_args.kwargs["content"], "revised turn")

        with patch("app.routers.junior_shared.store.update_thread", return_value=archived) as updated:
            closed = TestClient(app).post(
                f"/api/v1/junior/threads/{thread_id}",
                json={"title": "Closed chat", "status": "archived"},
            )
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.json()["status"], "archived")
        self.assertEqual(closed.json()["title"], "Closed chat")
        self.assertEqual(str(updated.call_args.args[2]), str(thread_id))
        self.assertEqual(updated.call_args.kwargs["status_value"], "archived")

    def test_search_and_memories(self):
        now = datetime.now(timezone.utc)
        hit = {
            "thread_id": uuid.uuid4(),
            "thread_title": "Finance",
            "message_id": uuid.uuid4(),
            "snippet": "equipment finance",
            "venue": "storykeep",
            "created_at": now,
            "rank": 0.8,
        }
        fact = SimpleNamespace(
            id=uuid.uuid4(),
            kind="preference",
            content="Prefers short replies",
            source_thread=None,
            created_at=now,
            updated_at=now,
        )
        app = _app()
        with patch("app.routers.junior_shared.store.search_page", return_value=([hit], None)):
            searched = TestClient(app).get("/api/v1/junior/search", params={"q": "equipment finance"})
        self.assertEqual(searched.status_code, 200)
        self.assertEqual(searched.json()[0]["snippet"], "equipment finance")

        with patch("app.routers.junior_shared.store.search_hit_owned", return_value=hit) as owned_hit:
            one_hit = TestClient(app).get(f"/api/v1/junior/search/{hit['message_id']}")
        self.assertEqual(one_hit.status_code, 200)
        self.assertEqual(one_hit.json()["snippet"], "equipment finance")
        self.assertEqual(str(owned_hit.call_args.args[2]), str(hit["message_id"]))

        pinned = {**hit, "snippet": "pinned snippet"}
        with patch("app.routers.junior_shared.store.update_search_hit", return_value=pinned) as updated_hit:
            changed_hit = TestClient(app).post(
                f"/api/v1/junior/search/{hit['message_id']}",
                json={"snippet": "pinned snippet"},
            )
        self.assertEqual(changed_hit.status_code, 200)
        self.assertEqual(changed_hit.json()["snippet"], "pinned snippet")
        self.assertEqual(str(updated_hit.call_args.args[2]), str(hit["message_id"]))
        self.assertEqual(updated_hit.call_args.kwargs["snippet"], "pinned snippet")

        with patch("app.routers.junior_shared.store.list_memories_page", return_value=([fact], None)):
            listed = TestClient(app).get("/api/v1/junior/memories")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["kind"], "preference")

        with patch("app.routers.junior_shared.store.upsert_memory", return_value=fact):
            saved = TestClient(app).post(
                "/api/v1/junior/memories",
                json={"kind": "preference", "content": "Prefers short replies"},
            )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["content"], "Prefers short replies")

        with patch("app.routers.junior_shared.store.memory_owned", return_value=fact) as owned:
            one = TestClient(app).get(f"/api/v1/junior/memories/{fact.id}")
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["content"], "Prefers short replies")
        self.assertEqual(str(owned.call_args.args[2]), str(fact.id))

        revised = SimpleNamespace(
            id=fact.id,
            kind="note",
            content="Prefers shorter replies",
            source_thread=None,
            created_at=now,
            updated_at=now,
        )
        with patch("app.routers.junior_shared.store.update_memory", return_value=revised) as updated:
            patched = TestClient(app).post(
                f"/api/v1/junior/memories/{fact.id}",
                json={"kind": "note", "content": "Prefers shorter replies"},
            )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["content"], "Prefers shorter replies")
        self.assertEqual(str(updated.call_args.args[2]), str(fact.id))

        thread_id = uuid.uuid4()
        scoped = SimpleNamespace(
            id=fact.id,
            kind="note",
            content="Prefers shorter replies",
            source_thread=thread_id,
            created_at=now,
            updated_at=now,
        )
        with patch("app.routers.junior_shared.store.thread_memory_owned", return_value=scoped) as owned_thread:
            nested = TestClient(app).get(f"/api/v1/junior/threads/{thread_id}/memories/{fact.id}")
        self.assertEqual(nested.status_code, 200)
        self.assertEqual(nested.json()["content"], "Prefers shorter replies")
        self.assertEqual(str(owned_thread.call_args.args[2]), str(thread_id))
        self.assertEqual(str(owned_thread.call_args.args[3]), str(fact.id))

        with patch(
            "app.routers.junior_shared.store.update_thread_memory", return_value=scoped
        ) as thread_updated:
            changed = TestClient(app).post(
                f"/api/v1/junior/threads/{thread_id}/memories/{fact.id}",
                json={"content": "Prefers shorter replies", "kind": "note"},
            )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["content"], "Prefers shorter replies")
        self.assertEqual(str(thread_updated.call_args.args[2]), str(thread_id))
        self.assertEqual(str(thread_updated.call_args.args[3]), str(fact.id))
        self.assertEqual(thread_updated.call_args.kwargs["content"], "Prefers shorter replies")

        with patch(
            "app.routers.junior_shared.store.list_memories_page",
            return_value=([scoped], str(fact.id)),
        ) as listed, patch("app.routers.junior_shared.store.thread_owned", return_value=SimpleNamespace(id=thread_id)):
            page = TestClient(app).get(
                f"/api/v1/junior/threads/{thread_id}/memories",
                params={"limit": 1, "cursor": str(fact.id)},
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()[0]["content"], "Prefers shorter replies")
        self.assertEqual(page.headers.get("x-next-cursor"), str(fact.id))
        self.assertEqual(listed.call_args.kwargs["source_thread"], thread_id)
        self.assertEqual(listed.call_args.kwargs["limit"], 1)

        with patch("app.routers.junior_shared.store.create_thread_memory", return_value=scoped) as created:
            saved = TestClient(app).post(
                f"/api/v1/junior/threads/{thread_id}/memories",
                json={"content": "Prefers shorter replies", "kind": "note", "source_thread": str(uuid.uuid4())},
            )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["content"], "Prefers shorter replies")
        self.assertEqual(created.call_args.args[2], thread_id)
        self.assertEqual(created.call_args.kwargs["content"], "Prefers shorter replies")
        self.assertEqual(created.call_args.kwargs["kind"], "note")


class JuniorSharedServiceTests(unittest.TestCase):
    def test_invalid_venue_and_kind(self):
        with self.assertRaises(HTTPException) as venue_err:
            store.normalize_venue("xbox")
        self.assertEqual(venue_err.exception.status_code, 400)
        with self.assertRaises(HTTPException) as kind_err:
            store.normalize_kind("secret")
        self.assertEqual(kind_err.exception.status_code, 400)

    def test_thread_owned_is_404_for_other_user(self):
        owner = _owner()
        other = uuid.uuid4()
        db = MagicMock()
        db.get.return_value = SimpleNamespace(id=uuid.uuid4(), user_id=other)
        with self.assertRaises(HTTPException) as caught:
            store.thread_owned(db, owner, uuid.uuid4())
        self.assertEqual(caught.exception.status_code, 404)

    def test_memory_owned_is_404_for_other_user(self):
        owner = _owner()
        other = uuid.uuid4()
        db = MagicMock()
        db.get.return_value = SimpleNamespace(id=uuid.uuid4(), user_id=other)
        with self.assertRaises(HTTPException) as caught:
            store.memory_owned(db, owner, uuid.uuid4())
        self.assertEqual(caught.exception.status_code, 404)

    def test_agent_run_owned_is_404_for_other_user(self):
        owner = _owner()
        other = uuid.uuid4()
        db = MagicMock()
        db.get.return_value = SimpleNamespace(id=uuid.uuid4(), user_id=other)
        with self.assertRaises(HTTPException) as caught:
            store.agent_run_owned(db, owner, uuid.uuid4())
        self.assertEqual(caught.exception.status_code, 404)

    def test_message_owned_is_404_for_other_user(self):
        owner = _owner()
        other = uuid.uuid4()
        db = MagicMock()
        db.get.side_effect = [
            SimpleNamespace(id=uuid.uuid4(), thread_id=uuid.uuid4()),
            SimpleNamespace(id=uuid.uuid4(), user_id=other),
        ]
        with self.assertRaises(HTTPException) as caught:
            store.message_owned(db, owner, uuid.uuid4())
        self.assertEqual(caught.exception.status_code, 404)

    def test_update_thread_message_is_404_when_thread_mismatches(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        other_thread = uuid.uuid4()
        message_id = uuid.uuid4()
        db = MagicMock()
        db.get.side_effect = [
            SimpleNamespace(id=thread_id, user_id=owner.id),
            SimpleNamespace(id=message_id, thread_id=other_thread),
            SimpleNamespace(id=other_thread, user_id=owner.id),
        ]
        with self.assertRaises(HTTPException) as caught:
            store.update_thread_message(db, owner, thread_id, message_id, content="revised turn")
        self.assertEqual(caught.exception.status_code, 404)

    def test_update_message_is_404_for_other_user(self):
        owner = _owner()
        other = uuid.uuid4()
        db = MagicMock()
        db.get.side_effect = [
            SimpleNamespace(id=uuid.uuid4(), thread_id=uuid.uuid4()),
            SimpleNamespace(id=uuid.uuid4(), user_id=other),
        ]
        with self.assertRaises(HTTPException) as caught:
            store.update_message(db, owner, uuid.uuid4(), content="revised turn")
        self.assertEqual(caught.exception.status_code, 404)

    def test_thread_search_hit_owned_is_404_when_thread_mismatches(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        other_thread = uuid.uuid4()
        message_id = uuid.uuid4()
        message = SimpleNamespace(
            id=message_id,
            thread_id=other_thread,
            content="hi",
            venue="phone",
            created_at=None,
            meta={},
        )
        db = MagicMock()
        db.get.side_effect = [
            SimpleNamespace(id=thread_id, user_id=owner.id),
            message,
            SimpleNamespace(id=other_thread, user_id=owner.id, title="other"),
        ]
        with self.assertRaises(HTTPException) as caught:
            store.thread_search_hit_owned(db, owner, thread_id, message_id)
        self.assertEqual(caught.exception.status_code, 404)

    def test_list_project_memories_uses_project_threads(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        project = SimpleNamespace(slug="storykeep", meta={})
        with patch("app.services.junior_shared_memory.get_project", return_value=project), patch(
            "app.services.junior_shared_memory.project_search_thread_ids",
            return_value=[thread_id],
        ), patch(
            "app.services.junior_shared_memory.list_memories_page",
            return_value=([], None),
        ) as listed:
            rows, cursor = store.list_project_memories_page(object(), owner, "storykeep", limit=2)
        self.assertEqual(rows, [])
        self.assertIsNone(cursor)
        self.assertEqual(listed.call_args.kwargs["source_threads"], [thread_id])
        self.assertEqual(listed.call_args.kwargs["limit"], 2)

    def test_create_project_memory_uses_pinned_thread(self):
        owner = _owner()
        pinned = uuid.uuid4()
        other = uuid.uuid4()
        saved = SimpleNamespace(id=uuid.uuid4(), content="keep")
        project = SimpleNamespace(slug="storykeep", meta={"context_thread_id": str(pinned)})
        with patch("app.services.junior_shared_memory.get_project", return_value=project), patch(
            "app.services.junior_shared_memory.project_search_thread_ids",
            return_value=[pinned, other],
        ), patch("app.services.junior_shared_memory.upsert_memory", return_value=saved) as created:
            row = store.create_project_memory(object(), owner, "storykeep", kind="note", content="keep")
        self.assertIs(row, saved)
        self.assertEqual(created.call_args.kwargs["source_thread"], pinned)
        self.assertEqual(created.call_args.kwargs["content"], "keep")
        self.assertIsNone(created.call_args.kwargs["memory_id"])

        with patch("app.services.junior_shared_memory.get_project", return_value=project), patch(
            "app.services.junior_shared_memory.project_search_thread_ids",
            return_value=[],
        ):
            with self.assertRaises(HTTPException) as caught:
                store.create_project_memory(object(), owner, "storykeep", kind="note", content="keep")
        self.assertEqual(caught.exception.status_code, 404)

    def test_list_project_messages_uses_project_threads(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        project = SimpleNamespace(slug="storykeep", meta={})
        with patch("app.services.junior_shared_memory.get_project", return_value=project), patch(
            "app.services.junior_shared_memory.project_search_thread_ids",
            return_value=[thread_id],
        ), patch(
            "app.services.junior_shared_memory.list_recent_messages_page",
            return_value=([], None),
        ) as listed:
            rows, cursor = store.list_project_messages_page(object(), owner, "storykeep", limit=2)
        self.assertEqual(rows, [])
        self.assertIsNone(cursor)
        self.assertEqual(listed.call_args.kwargs["thread_ids"], [thread_id])
        self.assertEqual(listed.call_args.kwargs["limit"], 2)

    def test_create_project_message_uses_pinned_thread(self):
        owner = _owner()
        pinned = uuid.uuid4()
        other = uuid.uuid4()
        saved = (SimpleNamespace(id=pinned), SimpleNamespace(id=uuid.uuid4()), None, "stub")
        project = SimpleNamespace(slug="storykeep", meta={"context_thread_id": str(pinned)})
        with patch("app.services.junior_shared_memory.get_project", return_value=project), patch(
            "app.services.junior_shared_memory.project_search_thread_ids",
            return_value=[pinned, other],
        ), patch("app.services.junior_shared_memory.post_turn", return_value=saved) as posted:
            row = store.create_project_message(
                object(),
                owner,
                "storykeep",
                content="Remember the trailer quote",
                venue="phone",
                meta={"source": "phone"},
                device_label="junior-mobile",
            )
        self.assertIs(row, saved)
        self.assertEqual(posted.call_args.kwargs["thread_id"], pinned)
        self.assertEqual(posted.call_args.kwargs["content"], "Remember the trailer quote")
        self.assertEqual(posted.call_args.kwargs["venue"], "phone")

        with patch("app.services.junior_shared_memory.get_project", return_value=project), patch(
            "app.services.junior_shared_memory.project_search_thread_ids",
            return_value=[],
        ):
            with self.assertRaises(HTTPException) as caught:
                store.create_project_message(
                    object(),
                    owner,
                    "storykeep",
                    content="Remember the trailer quote",
                    venue="phone",
                    meta={},
                )
        self.assertEqual(caught.exception.status_code, 404)

    def test_project_continue_uses_pinned_thread(self):
        owner = _owner()
        pinned = uuid.uuid4()
        other = uuid.uuid4()
        thread = SimpleNamespace(id=pinned)
        project = SimpleNamespace(slug="storykeep", meta={"context_thread_id": str(pinned)})
        with patch("app.services.junior_shared_memory.get_project", return_value=project), patch(
            "app.services.junior_shared_memory.project_search_thread_ids",
            return_value=[pinned, other],
        ), patch("app.services.junior_shared_memory.thread_owned", return_value=thread) as owned:
            row = store.project_continue_thread(object(), owner, "storykeep")
        self.assertIs(row, thread)
        self.assertEqual(owned.call_args.args[2], pinned)

        with patch("app.services.junior_shared_memory.get_project", return_value=project), patch(
            "app.services.junior_shared_memory.project_search_thread_ids",
            return_value=[],
        ):
            with self.assertRaises(HTTPException) as caught:
                store.project_continue_thread(object(), owner, "storykeep")
        self.assertEqual(caught.exception.status_code, 404)

    def test_project_thread_owned_is_404_when_not_on_project(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        row = SimpleNamespace(id=thread_id, user_id=owner.id, title="other")
        project = SimpleNamespace(slug="storykeep", meta={})
        with patch("app.services.junior_shared_memory.get_project", return_value=project), patch(
            "app.services.junior_shared_memory.project_search_thread_ids",
            return_value=[uuid.uuid4()],
        ), patch("app.services.junior_shared_memory.thread_owned", return_value=row):
            with self.assertRaises(HTTPException) as caught:
                store.project_thread_owned(object(), owner, "storykeep", thread_id)
        self.assertEqual(caught.exception.status_code, 404)

    def test_update_project_thread_uses_project_scope(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        row = SimpleNamespace(id=thread_id, title="Storykeep", status="open")
        with patch("app.services.junior_shared_memory.project_thread_owned", return_value=row), patch(
            "app.services.junior_shared_memory.update_thread",
            return_value=row,
        ) as updated:
            store.update_project_thread(
                object(),
                owner,
                "storykeep",
                thread_id,
                title="Renamed",
                status_value="archived",
            )
        self.assertEqual(updated.call_args.args[2], thread_id)
        self.assertEqual(updated.call_args.kwargs["title"], "Renamed")
        self.assertEqual(updated.call_args.kwargs["status_value"], "archived")

    def test_project_search_thread_ids_include_opened_threads(self):
        owner = _owner()
        pinned = uuid.uuid4()
        opened = uuid.uuid4()
        foreign = uuid.uuid4()
        rows = {
            pinned: SimpleNamespace(id=pinned, user_id=owner.id),
            opened: SimpleNamespace(id=opened, user_id=owner.id),
            foreign: SimpleNamespace(id=foreign, user_id=uuid.uuid4()),
        }
        project = SimpleNamespace(
            slug="storykeep",
            meta={
                "context_thread_id": str(pinned),
                "project_thread_ids": [str(opened), str(pinned), str(foreign), "not-a-uuid"],
            },
        )

        class _Db:
            def get(self, _model, key):
                return rows.get(key)

            def scalars(self, _stmt):
                return []

        self.assertEqual(
            store.project_search_thread_ids(_Db(), owner, project),
            [pinned, opened],
        )

    def test_list_project_threads_uses_project_threads(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        project = SimpleNamespace(slug="storykeep", meta={})
        with patch("app.services.junior_shared_memory.get_project", return_value=project), patch(
            "app.services.junior_shared_memory.project_search_thread_ids",
            return_value=[thread_id],
        ), patch(
            "app.services.junior_shared_memory.list_threads_page",
            return_value=([], None),
        ) as listed:
            rows, cursor = store.list_project_threads_page(object(), owner, "storykeep", limit=2)
        self.assertEqual(rows, [])
        self.assertIsNone(cursor)
        self.assertEqual(listed.call_args.kwargs["thread_ids"], [thread_id])
        self.assertEqual(listed.call_args.kwargs["limit"], 2)

    def test_create_project_thread_pins_or_appends(self):
        owner = _owner()
        created = SimpleNamespace(id=uuid.uuid4())
        empty = SimpleNamespace(slug="storykeep", meta={}, updated_at=None)
        with patch("app.services.junior_shared_memory.get_project", return_value=empty), patch(
            "app.services.junior_shared_memory.create_thread",
            return_value=created,
        ):
            row = store.create_project_thread(
                SimpleNamespace(flush=lambda: None),
                owner,
                "storykeep",
                title="Lab notes",
                venue="phone",
                status_value="open",
            )
        self.assertIs(row, created)
        self.assertEqual(empty.meta["context_thread_id"], str(created.id))
        self.assertNotIn("project_thread_ids", empty.meta)

        pinned = uuid.uuid4()
        another = SimpleNamespace(id=uuid.uuid4())
        existing = SimpleNamespace(
            slug="storykeep",
            meta={"context_thread_id": str(pinned), "notes": "keep"},
            updated_at=None,
        )
        with patch("app.services.junior_shared_memory.get_project", return_value=existing), patch(
            "app.services.junior_shared_memory.create_thread",
            return_value=another,
        ):
            store.create_project_thread(
                SimpleNamespace(flush=lambda: None),
                owner,
                "storykeep",
                title="Second",
                venue="windows",
                status_value="open",
            )
        self.assertEqual(existing.meta["context_thread_id"], str(pinned))
        self.assertEqual(existing.meta["notes"], "keep")
        self.assertEqual(existing.meta["project_thread_ids"], [str(another.id)])

        with patch(
            "app.services.junior_shared_memory.get_project",
            side_effect=HTTPException(status_code=404, detail="Project not found"),
        ):
            with self.assertRaises(HTTPException) as caught:
                store.create_project_thread(
                    object(),
                    owner,
                    "missing",
                    title="Lab notes",
                    venue="phone",
                )
        self.assertEqual(caught.exception.status_code, 404)

    def test_project_threads_routes(self):
        now = datetime.now(timezone.utc)
        thread = SimpleNamespace(
            id=uuid.uuid4(),
            title="Lab notes",
            venue_last="phone",
            status="open",
            summary=None,
            created_at=now,
            updated_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.list_project_threads_page",
            return_value=([thread], str(thread.id)),
        ) as listed:
            page = TestClient(app).get(
                "/api/v1/junior/projects/storykeep/threads",
                params={"limit": 1, "cursor": str(thread.id), "before_id": str(thread.id)},
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()[0]["title"], "Lab notes")
        self.assertEqual(page.headers.get("x-next-cursor"), str(thread.id))
        self.assertEqual(listed.call_args.args[2], "storykeep")
        self.assertEqual(listed.call_args.kwargs["limit"], 1)

        with patch("app.routers.junior_shared.store.create_project_thread", return_value=thread) as created:
            opened = TestClient(app).post(
                "/api/v1/junior/projects/storykeep/threads",
                json={"title": "Lab notes", "venue": "phone", "status": "open"},
            )
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(opened.json()["id"], str(thread.id))
        self.assertEqual(created.call_args.args[2], "storykeep")
        self.assertEqual(created.call_args.kwargs["title"], "Lab notes")
        self.assertEqual(created.call_args.kwargs["venue"], "phone")
        self.assertEqual(created.call_args.kwargs["status_value"], "open")

        message = SimpleNamespace(
            id=uuid.uuid4(),
            thread_id=thread.id,
            role="user",
            content="Start here",
            venue="phone",
            meta={"source": "phone"},
            created_at=now,
        )
        with patch("app.routers.junior_shared.store.create_project_thread", return_value=thread), patch(
            "app.routers.junior_shared.store.post_turn",
            return_value=(thread, message, None, "stub"),
        ) as posted:
            saved = TestClient(app).post(
                "/api/v1/junior/projects/storykeep/threads",
                json={"title": "Lab notes", "text": "Start here", "venue": "phone", "meta": {"source": "phone"}},
            )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["thread_id"], str(thread.id))
        self.assertEqual(saved.json()["user_message"]["content"], "Start here")
        self.assertEqual(posted.call_args.kwargs["thread_id"], thread.id)
        self.assertEqual(posted.call_args.kwargs["content"], "Start here")

    def test_project_thread_message_owned_is_404_off_thread(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        message_id = uuid.uuid4()
        row = SimpleNamespace(id=message_id, thread_id=uuid.uuid4(), content="hi")
        with patch(
            "app.services.junior_shared_memory.project_thread_owned",
            return_value=SimpleNamespace(id=thread_id),
        ), patch("app.services.junior_shared_memory.message_owned", return_value=row):
            with self.assertRaises(HTTPException) as caught:
                store.project_thread_message_owned(
                    object(), owner, "storykeep", thread_id, message_id
                )
        self.assertEqual(caught.exception.status_code, 404)

    def test_update_project_thread_message_uses_thread_scope(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        message_id = uuid.uuid4()
        row = SimpleNamespace(id=message_id, thread_id=thread_id, content="keep")
        with patch(
            "app.services.junior_shared_memory.project_thread_message_owned",
            return_value=row,
        ), patch("app.services.junior_shared_memory.update_message", return_value=row) as updated:
            store.update_project_thread_message(
                object(),
                owner,
                "storykeep",
                thread_id,
                message_id,
                content="revised turn",
                venue="phone",
                meta={"source": "phone"},
                set_venue=True,
                set_meta=True,
            )
        self.assertEqual(updated.call_args.args[2], message_id)
        self.assertEqual(updated.call_args.kwargs["content"], "revised turn")
        self.assertTrue(updated.call_args.kwargs["set_venue"])
        self.assertTrue(updated.call_args.kwargs["set_meta"])

    def test_project_thread_message_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        message = SimpleNamespace(
            id=uuid.uuid4(),
            thread_id=thread_id,
            role="user",
            content="Remember the trailer quote",
            venue="phone",
            meta={"source": "phone"},
            created_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.project_thread_message_owned",
            return_value=message,
        ) as loaded:
            one = TestClient(app).get(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/messages/{message.id}"
            )
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["content"], "Remember the trailer quote")
        self.assertEqual(loaded.call_args.args[2], "storykeep")
        self.assertEqual(loaded.call_args.args[3], thread_id)
        self.assertEqual(loaded.call_args.args[4], message.id)

        revised = SimpleNamespace(
            id=message.id,
            thread_id=thread_id,
            role="user",
            content="revised turn",
            venue="phone",
            meta={"source": "phone"},
            created_at=now,
        )
        with patch(
            "app.routers.junior_shared.store.update_project_thread_message",
            return_value=revised,
        ) as updated:
            posted = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/messages/{message.id}",
                json={"text": "revised turn", "venue": "phone", "meta": {"source": "phone"}},
            )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()["content"], "revised turn")
        self.assertEqual(updated.call_args.args[2], "storykeep")
        self.assertEqual(updated.call_args.args[3], thread_id)
        self.assertEqual(updated.call_args.args[4], message.id)
        self.assertEqual(updated.call_args.kwargs["content"], "revised turn")
        self.assertTrue(updated.call_args.kwargs["set_venue"])
        self.assertEqual(updated.call_args.kwargs["venue"], "phone")
        self.assertTrue(updated.call_args.kwargs["set_meta"])

    def test_list_project_thread_messages_requires_thread_on_project(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        with patch(
            "app.services.junior_shared_memory.project_thread_owned",
            side_effect=HTTPException(status_code=404, detail="Thread not found"),
        ), patch("app.services.junior_shared_memory.list_messages_page") as listed:
            with self.assertRaises(HTTPException) as caught:
                store.list_project_thread_messages_page(object(), owner, "storykeep", thread_id, limit=2)
        self.assertEqual(caught.exception.status_code, 404)
        listed.assert_not_called()

        with patch(
            "app.services.junior_shared_memory.project_thread_owned",
            return_value=SimpleNamespace(id=thread_id),
        ), patch(
            "app.services.junior_shared_memory.list_messages_page",
            return_value=([], None),
        ) as listed:
            rows, cursor = store.list_project_thread_messages_page(
                object(), owner, "storykeep", thread_id, limit=2, cursor="abc"
            )
        self.assertEqual(rows, [])
        self.assertIsNone(cursor)
        self.assertEqual(listed.call_args.args[2], thread_id)
        self.assertEqual(listed.call_args.kwargs["limit"], 2)
        self.assertEqual(listed.call_args.kwargs["cursor"], "abc")

    def test_create_project_thread_message_uses_that_thread(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        saved = (SimpleNamespace(id=thread_id), SimpleNamespace(id=uuid.uuid4()), None, "stub")
        with patch(
            "app.services.junior_shared_memory.project_thread_owned",
            return_value=SimpleNamespace(id=thread_id),
        ), patch("app.services.junior_shared_memory.post_turn", return_value=saved) as posted:
            store.create_project_thread_message(
                object(),
                owner,
                "storykeep",
                thread_id,
                content="Remember the trailer quote",
                venue="phone",
                meta={"source": "phone"},
                device_label="junior-mobile",
            )
        self.assertEqual(posted.call_args.kwargs["thread_id"], thread_id)
        self.assertEqual(posted.call_args.kwargs["content"], "Remember the trailer quote")
        self.assertEqual(posted.call_args.kwargs["venue"], "phone")
        self.assertEqual(posted.call_args.kwargs["meta"], {"source": "phone"})
        self.assertEqual(posted.call_args.kwargs["device_label"], "junior-mobile")

        with patch(
            "app.services.junior_shared_memory.project_thread_owned",
            side_effect=HTTPException(status_code=404, detail="Thread not found"),
        ):
            with self.assertRaises(HTTPException) as caught:
                store.create_project_thread_message(
                    object(),
                    owner,
                    "missing",
                    thread_id,
                    content="no",
                    venue="phone",
                    meta=None,
                )
        self.assertEqual(caught.exception.status_code, 404)

    def test_project_thread_messages_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        message = SimpleNamespace(
            id=uuid.uuid4(),
            thread_id=thread_id,
            role="user",
            content="Remember the trailer quote",
            venue="phone",
            meta={"source": "phone"},
            created_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.list_project_thread_messages_page",
            return_value=([message], str(message.id)),
        ) as listed:
            page = TestClient(app).get(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/messages",
                params={"limit": 1, "cursor": str(message.id), "before_id": str(message.id)},
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()[0]["content"], "Remember the trailer quote")
        self.assertEqual(page.headers.get("x-next-cursor"), str(message.id))
        self.assertEqual(listed.call_args.args[2], "storykeep")
        self.assertEqual(listed.call_args.args[3], thread_id)
        self.assertEqual(listed.call_args.kwargs["limit"], 1)

        thread = SimpleNamespace(id=thread_id)
        with patch(
            "app.routers.junior_shared.store.create_project_thread_message",
            return_value=(thread, message, None, "stub"),
        ) as created:
            saved = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/messages",
                json={"text": "Remember the trailer quote", "venue": "phone", "meta": {"source": "phone"}},
            )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["thread_id"], str(thread_id))
        self.assertEqual(saved.json()["user_message"]["content"], "Remember the trailer quote")
        self.assertEqual(created.call_args.args[2], "storykeep")
        self.assertEqual(created.call_args.args[3], thread_id)
        self.assertEqual(created.call_args.kwargs["content"], "Remember the trailer quote")
        self.assertEqual(created.call_args.kwargs["venue"], "phone")
        self.assertEqual(created.call_args.kwargs["meta"], {"source": "phone"})

    def test_continue_project_thread_uses_that_thread(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        saved = (SimpleNamespace(id=thread_id), SimpleNamespace(id=uuid.uuid4()), None, "stub")
        with patch(
            "app.services.junior_shared_memory.project_thread_owned",
            return_value=SimpleNamespace(id=thread_id),
        ), patch("app.services.junior_shared_memory.post_turn", return_value=saved) as posted:
            row = store.continue_project_thread(
                object(),
                owner,
                "storykeep",
                thread_id,
                content="pick up the trailer",
                venue="phone",
                meta={"source": "phone"},
                device_label="junior-mobile",
            )
        self.assertEqual(row, saved)
        self.assertEqual(posted.call_args.kwargs["thread_id"], thread_id)
        self.assertEqual(posted.call_args.kwargs["content"], "pick up the trailer")
        self.assertEqual(posted.call_args.kwargs["venue"], "phone")
        self.assertEqual(posted.call_args.kwargs["meta"], {"source": "phone"})
        self.assertEqual(posted.call_args.kwargs["device_label"], "junior-mobile")

        with patch(
            "app.services.junior_shared_memory.project_thread_owned",
            side_effect=HTTPException(status_code=404, detail="Thread not found"),
        ), patch("app.services.junior_shared_memory.post_turn") as posted:
            with self.assertRaises(HTTPException) as caught:
                store.continue_project_thread(
                    object(),
                    owner,
                    "missing",
                    thread_id,
                    content="no",
                    venue="phone",
                    meta=None,
                )
        self.assertEqual(caught.exception.status_code, 404)
        posted.assert_not_called()

    def test_project_thread_continue_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        thread = SimpleNamespace(
            id=thread_id,
            title="Storykeep",
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
            content="pick up the trailer",
            venue="phone",
            meta={"source": "phone"},
            created_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.project_thread_owned",
            return_value=thread,
        ) as loaded, patch(
            "app.routers.junior_shared.store.list_messages_page",
            return_value=([message], str(message.id)),
        ) as history:
            page = TestClient(app).get(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/continue",
                params={"limit": 1, "cursor": str(message.id)},
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()["thread"]["id"], str(thread_id))
        self.assertEqual(page.json()["messages"][0]["content"], "pick up the trailer")
        self.assertIsNone(page.json()["user_message"])
        self.assertEqual(page.headers.get("x-next-cursor"), str(message.id))
        self.assertEqual(loaded.call_args.args[2], "storykeep")
        self.assertEqual(loaded.call_args.args[3], thread_id)
        self.assertEqual(history.call_args.kwargs["limit"], 1)

        with patch(
            "app.routers.junior_shared.store.project_thread_owned",
            return_value=thread,
        ), patch(
            "app.routers.junior_shared.store.continue_project_thread",
            return_value=(thread, message, None, "stubbed_no_key"),
        ) as posted, patch(
            "app.routers.junior_shared.store.list_messages_page",
            return_value=([message], None),
        ):
            saved = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/continue",
                json={"text": "pick up the trailer", "venue": "phone", "meta": {"source": "phone"}},
            )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["thread"]["id"], str(thread_id))
        self.assertEqual(saved.json()["user_message"]["content"], "pick up the trailer")
        self.assertEqual(posted.call_args.args[2], "storykeep")
        self.assertEqual(posted.call_args.args[3], thread_id)
        self.assertEqual(posted.call_args.kwargs["content"], "pick up the trailer")
        self.assertEqual(posted.call_args.kwargs["venue"], "phone")
        self.assertEqual(posted.call_args.kwargs["meta"], {"source": "phone"})

        with patch(
            "app.routers.junior_shared.store.project_thread_owned",
            side_effect=HTTPException(status_code=404, detail="Thread not found"),
        ):
            missing = TestClient(app).get(
                f"/api/v1/junior/projects/missing/threads/{thread_id}/continue"
            )
        self.assertEqual(missing.status_code, 404)

    def test_project_thread_routes(self):
        now = datetime.now(timezone.utc)
        thread = SimpleNamespace(
            id=uuid.uuid4(),
            title="Storykeep",
            venue_last="phone",
            status="open",
            summary=None,
            created_at=now,
            updated_at=now,
        )
        app = _app()
        with patch("app.routers.junior_shared.store.project_thread_owned", return_value=thread) as loaded:
            one = TestClient(app).get(f"/api/v1/junior/projects/storykeep/threads/{thread.id}")
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["title"], "Storykeep")
        self.assertEqual(loaded.call_args.args[2], "storykeep")
        self.assertEqual(loaded.call_args.args[3], thread.id)

        revised = SimpleNamespace(
            id=thread.id,
            title="Renamed",
            venue_last="phone",
            status="archived",
            summary=None,
            created_at=now,
            updated_at=now,
        )
        with patch("app.routers.junior_shared.store.update_project_thread", return_value=revised) as updated:
            posted = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/threads/{thread.id}",
                json={"title": "Renamed", "status": "archived"},
            )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()["title"], "Renamed")
        self.assertEqual(posted.json()["status"], "archived")
        self.assertEqual(updated.call_args.args[2], "storykeep")
        self.assertEqual(updated.call_args.args[3], thread.id)
        self.assertEqual(updated.call_args.kwargs["title"], "Renamed")
        self.assertEqual(updated.call_args.kwargs["status_value"], "archived")

    def test_project_continue_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        thread = SimpleNamespace(
            id=thread_id,
            title="Storykeep",
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
            content="pick up the trailer",
            venue="phone",
            meta={"source": "phone"},
            created_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.project_continue_thread",
            return_value=thread,
        ) as loaded, patch(
            "app.routers.junior_shared.store.list_messages_page",
            return_value=([message], str(message.id)),
        ) as history:
            page = TestClient(app).get(
                "/api/v1/junior/projects/storykeep/continue",
                params={"limit": 1, "cursor": str(message.id)},
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()["thread"]["id"], str(thread_id))
        self.assertEqual(page.json()["messages"][0]["content"], "pick up the trailer")
        self.assertIsNone(page.json()["user_message"])
        self.assertEqual(page.headers.get("x-next-cursor"), str(message.id))
        self.assertEqual(loaded.call_args.args[2], "storykeep")
        self.assertEqual(history.call_args.kwargs["limit"], 1)

        with patch(
            "app.routers.junior_shared.store.project_continue_thread",
            return_value=thread,
        ), patch(
            "app.routers.junior_shared.store.post_turn",
            return_value=(thread, message, None, "stubbed_no_key"),
        ) as posted, patch(
            "app.routers.junior_shared.store.list_messages_page",
            return_value=([message], None),
        ):
            saved = TestClient(app).post(
                "/api/v1/junior/projects/storykeep/continue",
                json={"text": "pick up the trailer", "venue": "phone", "meta": {"source": "phone"}},
            )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["thread"]["id"], str(thread_id))
        self.assertEqual(saved.json()["user_message"]["content"], "pick up the trailer")
        self.assertEqual(posted.call_args.kwargs["thread_id"], thread_id)
        self.assertEqual(posted.call_args.kwargs["content"], "pick up the trailer")
        self.assertEqual(posted.call_args.kwargs["venue"], "phone")
        self.assertEqual(posted.call_args.kwargs["meta"], {"source": "phone"})

    def test_project_messages_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        message = SimpleNamespace(
            id=uuid.uuid4(),
            thread_id=thread_id,
            role="user",
            content="Remember the trailer quote",
            venue="phone",
            meta={"source": "phone"},
            created_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.list_project_messages_page",
            return_value=([message], str(message.id)),
        ) as listed:
            page = TestClient(app).get(
                "/api/v1/junior/projects/storykeep/messages",
                params={"limit": 1, "cursor": str(message.id), "before_id": str(message.id)},
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()[0]["content"], "Remember the trailer quote")
        self.assertEqual(page.headers.get("x-next-cursor"), str(message.id))
        self.assertEqual(listed.call_args.args[2], "storykeep")
        self.assertEqual(listed.call_args.kwargs["limit"], 1)

        thread = SimpleNamespace(id=thread_id)
        with patch(
            "app.routers.junior_shared.store.create_project_message",
            return_value=(thread, message, None, "stub"),
        ) as created:
            saved = TestClient(app).post(
                "/api/v1/junior/projects/storykeep/messages",
                json={"text": "Remember the trailer quote", "venue": "phone", "meta": {"source": "phone"}},
            )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["thread_id"], str(thread_id))
        self.assertEqual(saved.json()["user_message"]["content"], "Remember the trailer quote")
        self.assertEqual(created.call_args.args[2], "storykeep")
        self.assertEqual(created.call_args.kwargs["content"], "Remember the trailer quote")
        self.assertEqual(created.call_args.kwargs["venue"], "phone")
        self.assertEqual(created.call_args.kwargs["meta"], {"source": "phone"})

    def test_project_message_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        message = SimpleNamespace(
            id=uuid.uuid4(),
            thread_id=thread_id,
            role="user",
            content="Remember the trailer quote",
            venue="phone",
            meta={"source": "phone"},
            created_at=now,
        )
        app = _app()
        with patch("app.routers.junior_shared.store.project_message_owned", return_value=message) as loaded:
            one = TestClient(app).get(f"/api/v1/junior/projects/storykeep/messages/{message.id}")
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["content"], "Remember the trailer quote")
        self.assertEqual(loaded.call_args.args[2], "storykeep")
        self.assertEqual(loaded.call_args.args[3], message.id)

        revised = SimpleNamespace(
            id=message.id,
            thread_id=thread_id,
            role="user",
            content="revised turn",
            venue="phone",
            meta={"source": "phone"},
            created_at=now,
        )
        with patch("app.routers.junior_shared.store.update_project_message", return_value=revised) as updated:
            posted = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/messages/{message.id}",
                json={"text": "revised turn", "venue": "phone", "meta": {"source": "phone"}},
            )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()["content"], "revised turn")
        self.assertEqual(updated.call_args.args[2], "storykeep")
        self.assertEqual(updated.call_args.args[3], message.id)
        self.assertEqual(updated.call_args.kwargs["content"], "revised turn")
        self.assertTrue(updated.call_args.kwargs["set_venue"])
        self.assertEqual(updated.call_args.kwargs["venue"], "phone")
        self.assertTrue(updated.call_args.kwargs["set_meta"])

    def test_project_message_owned_is_404_when_not_on_project(self):
        owner = _owner()
        message_id = uuid.uuid4()
        other_thread = uuid.uuid4()
        row = SimpleNamespace(id=message_id, thread_id=other_thread, content="hi")
        project = SimpleNamespace(slug="storykeep", meta={})
        with patch("app.services.junior_shared_memory.get_project", return_value=project), patch(
            "app.services.junior_shared_memory.project_search_thread_ids",
            return_value=[uuid.uuid4()],
        ), patch("app.services.junior_shared_memory.message_owned", return_value=row):
            with self.assertRaises(HTTPException) as caught:
                store.project_message_owned(object(), owner, "storykeep", message_id)
        self.assertEqual(caught.exception.status_code, 404)

    def test_update_project_message_uses_project_scope(self):
        owner = _owner()
        message_id = uuid.uuid4()
        thread_id = uuid.uuid4()
        row = SimpleNamespace(id=message_id, thread_id=thread_id, content="keep")
        with patch("app.services.junior_shared_memory.project_message_owned", return_value=row), patch(
            "app.services.junior_shared_memory.update_message",
            return_value=row,
        ) as updated:
            store.update_project_message(
                object(),
                owner,
                "storykeep",
                message_id,
                content="revised turn",
                venue="phone",
                meta={"source": "phone"},
                set_venue=True,
                set_meta=True,
            )
        self.assertEqual(updated.call_args.args[2], message_id)
        self.assertEqual(updated.call_args.kwargs["content"], "revised turn")
        self.assertTrue(updated.call_args.kwargs["set_venue"])
        self.assertTrue(updated.call_args.kwargs["set_meta"])

    def test_list_project_thread_memories_uses_thread_scope(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        with patch(
            "app.services.junior_shared_memory.project_thread_owned",
            return_value=SimpleNamespace(id=thread_id),
        ), patch(
            "app.services.junior_shared_memory.list_memories_page",
            return_value=([], None),
        ) as listed:
            rows, cursor = store.list_project_thread_memories_page(
                object(), owner, "storykeep", thread_id, kind="note", limit=2
            )
        self.assertEqual(rows, [])
        self.assertIsNone(cursor)
        self.assertEqual(listed.call_args.kwargs["source_thread"], thread_id)
        self.assertEqual(listed.call_args.kwargs["kind"], "note")
        self.assertEqual(listed.call_args.kwargs["limit"], 2)

    def test_create_project_thread_memory_uses_thread_scope(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        saved = SimpleNamespace(id=uuid.uuid4(), content="keep", source_thread=thread_id)
        with patch(
            "app.services.junior_shared_memory.project_thread_owned",
            return_value=SimpleNamespace(id=thread_id),
        ), patch(
            "app.services.junior_shared_memory.upsert_memory",
            return_value=saved,
        ) as created:
            row = store.create_project_thread_memory(
                object(),
                owner,
                "storykeep",
                thread_id,
                kind="note",
                content="keep",
            )
        self.assertIs(row, saved)
        self.assertIsNone(created.call_args.kwargs["memory_id"])
        self.assertEqual(created.call_args.kwargs["source_thread"], thread_id)
        self.assertEqual(created.call_args.kwargs["content"], "keep")
        self.assertEqual(created.call_args.kwargs["kind"], "note")

    def test_project_thread_memory_owned_is_404_off_thread(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        memory_id = uuid.uuid4()
        row = SimpleNamespace(
            id=memory_id,
            user_id=owner.id,
            source_thread=uuid.uuid4(),
            content="note",
            kind="note",
        )
        with patch(
            "app.services.junior_shared_memory.project_thread_owned",
            return_value=SimpleNamespace(id=thread_id),
        ), patch("app.services.junior_shared_memory.memory_owned", return_value=row):
            with self.assertRaises(HTTPException) as caught:
                store.project_thread_memory_owned(object(), owner, "storykeep", thread_id, memory_id)
        self.assertEqual(caught.exception.status_code, 404)

    def test_update_project_thread_memory_uses_thread_scope(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        memory_id = uuid.uuid4()
        row = SimpleNamespace(
            id=memory_id,
            kind="note",
            content="keep",
            source_thread=thread_id,
        )
        with patch(
            "app.services.junior_shared_memory.project_thread_memory_owned",
            return_value=row,
        ), patch("app.services.junior_shared_memory.update_memory", return_value=row) as updated:
            store.update_project_thread_memory(
                object(),
                owner,
                "storykeep",
                thread_id,
                memory_id,
                content="revised fact",
                kind="note",
                source_thread=thread_id,
                set_kind=True,
                set_source_thread=True,
            )
        self.assertEqual(updated.call_args.args[2], memory_id)
        self.assertEqual(updated.call_args.kwargs["content"], "revised fact")
        self.assertTrue(updated.call_args.kwargs["set_kind"])
        self.assertTrue(updated.call_args.kwargs["set_source_thread"])

    def test_list_project_thread_agents_uses_thread_scope(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        with patch(
            "app.services.junior_shared_memory.get_project",
            return_value=SimpleNamespace(slug="storykeep"),
        ), patch(
            "app.services.junior_shared_memory.project_thread_owned",
            return_value=SimpleNamespace(id=thread_id),
        ), patch(
            "app.services.junior_shared_memory.list_agent_runs_page",
            return_value=([], None),
        ) as listed:
            rows, cursor = store.list_project_thread_agents_page(
                object(), owner, "storykeep", thread_id, limit=2
            )
        self.assertEqual(rows, [])
        self.assertIsNone(cursor)
        self.assertEqual(listed.call_args.kwargs["project_slug"], "storykeep")
        self.assertEqual(listed.call_args.kwargs["thread_id"], thread_id)
        self.assertEqual(listed.call_args.kwargs["limit"], 2)

    def test_create_project_thread_agent_uses_thread_scope(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        run = SimpleNamespace(id=uuid.uuid4(), thread_id=thread_id, project_slug="storykeep")
        pack = {"project": SimpleNamespace(slug="storykeep"), "thread": run}
        with patch(
            "app.services.junior_shared_memory.project_thread_owned",
            return_value=SimpleNamespace(id=thread_id),
        ), patch(
            "app.services.junior_shared_memory.record_agent_run",
            return_value=(run, pack),
        ) as created:
            saved, context = store.create_project_thread_agent(
                object(),
                owner,
                "storykeep",
                thread_id,
                prompt="Fix the memory API",
                query="memory",
            )
        self.assertIs(saved, run)
        self.assertIs(context, pack)
        self.assertEqual(created.call_args.kwargs["project_slug"], "storykeep")
        self.assertEqual(created.call_args.kwargs["thread_id"], thread_id)
        self.assertEqual(created.call_args.kwargs["prompt"], "Fix the memory API")
        self.assertEqual(created.call_args.kwargs["query"], "memory")

    def test_project_thread_agent_owned_is_404_off_thread(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        run_id = uuid.uuid4()
        row = SimpleNamespace(
            id=run_id,
            user_id=owner.id,
            thread_id=uuid.uuid4(),
            project_slug="storykeep",
            prompt="Fix the memory API",
            status="context_ready",
        )
        with patch(
            "app.services.junior_shared_memory.get_project",
            return_value=SimpleNamespace(slug="storykeep"),
        ), patch(
            "app.services.junior_shared_memory.project_thread_owned",
            return_value=SimpleNamespace(id=thread_id),
        ), patch("app.services.junior_shared_memory.agent_run_owned", return_value=row):
            with self.assertRaises(HTTPException) as caught:
                store.project_thread_agent_owned(object(), owner, "storykeep", thread_id, run_id)
        self.assertEqual(caught.exception.status_code, 404)

    def test_project_thread_agent_owned_is_404_off_project(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        run_id = uuid.uuid4()
        row = SimpleNamespace(
            id=run_id,
            user_id=owner.id,
            thread_id=thread_id,
            project_slug="other",
            prompt="Fix the memory API",
            status="context_ready",
        )
        with patch(
            "app.services.junior_shared_memory.get_project",
            return_value=SimpleNamespace(slug="storykeep"),
        ), patch(
            "app.services.junior_shared_memory.project_thread_owned",
            return_value=SimpleNamespace(id=thread_id),
        ), patch("app.services.junior_shared_memory.agent_run_owned", return_value=row):
            with self.assertRaises(HTTPException) as caught:
                store.project_thread_agent_owned(object(), owner, "storykeep", thread_id, run_id)
        self.assertEqual(caught.exception.status_code, 404)

    def test_update_project_thread_agent_uses_thread_scope(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        run_id = uuid.uuid4()
        row = SimpleNamespace(id=run_id, thread_id=thread_id, project_slug="storykeep", status="launched")
        with patch(
            "app.services.junior_shared_memory.project_thread_agent_owned",
            return_value=row,
        ), patch("app.services.junior_shared_memory.update_agent_run", return_value=row) as updated:
            store.update_project_thread_agent(
                object(),
                owner,
                "storykeep",
                thread_id,
                run_id,
                prompt="Keep going",
                status_value="launched",
                set_status=True,
            )
        self.assertEqual(updated.call_args.args[2], run_id)
        self.assertEqual(updated.call_args.kwargs["prompt"], "Keep going")
        self.assertEqual(updated.call_args.kwargs["status_value"], "launched")
        self.assertTrue(updated.call_args.kwargs["set_status"])

    def test_project_thread_agents_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        run = SimpleNamespace(
            id=uuid.uuid4(),
            project_slug="storykeep",
            prompt="Fix the memory API",
            status="context_ready",
            cursor_agent_id=None,
            thread_id=thread_id,
            created_at=now,
        )
        pack = {
            "project": SimpleNamespace(
                id=uuid.uuid4(),
                slug="storykeep",
                display_name="StoryKeep",
                kind="app",
                repo_url=None,
                default_branch="main",
                notes=None,
                meta={},
                created_at=now,
                updated_at=now,
            ),
            "thread_summary": None,
            "recent_messages": [],
            "memories": [],
            "search_hits": [],
            "launch_hint": "record only",
        }
        app = _app()
        with patch(
            "app.routers.junior_shared.store.list_project_thread_agents_page",
            return_value=([run], str(run.id)),
        ) as listed:
            page = TestClient(app).get(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/agents",
                params={"limit": 1, "cursor": str(run.id)},
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()[0]["prompt"], "Fix the memory API")
        self.assertEqual(page.headers.get("x-next-cursor"), str(run.id))
        self.assertEqual(listed.call_args.args[2], "storykeep")
        self.assertEqual(listed.call_args.args[3], thread_id)
        self.assertEqual(listed.call_args.kwargs["limit"], 1)

        with patch(
            "app.routers.junior_shared.store.create_project_thread_agent",
            return_value=(run, pack),
        ) as created:
            saved = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/agents",
                json={"prompt": "Fix the memory API", "q": "memory"},
            )
        self.assertEqual(saved.status_code, 200)
        self.assertFalse(saved.json()["called_cursor_api"])
        self.assertEqual(saved.json()["run"]["status"], "context_ready")
        self.assertEqual(created.call_args.args[2], "storykeep")
        self.assertEqual(created.call_args.args[3], thread_id)
        self.assertEqual(created.call_args.kwargs["prompt"], "Fix the memory API")
        self.assertEqual(created.call_args.kwargs["query"], "memory")

    def test_project_thread_agent_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        run = SimpleNamespace(
            id=uuid.uuid4(),
            project_slug="storykeep",
            prompt="Fix the memory API",
            status="context_ready",
            cursor_agent_id=None,
            thread_id=thread_id,
            created_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.project_thread_agent_owned",
            return_value=run,
        ) as loaded:
            one = TestClient(app).get(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/agents/{run.id}"
            )
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["status"], "context_ready")
        self.assertEqual(str(one.json()["thread_id"]), str(thread_id))
        self.assertEqual(loaded.call_args.args[2], "storykeep")
        self.assertEqual(loaded.call_args.args[3], thread_id)
        self.assertEqual(loaded.call_args.args[4], run.id)

        launched = SimpleNamespace(
            id=run.id,
            project_slug="storykeep",
            prompt="Keep going",
            status="launched",
            cursor_agent_id="bc-thread",
            thread_id=thread_id,
            created_at=now,
        )
        with patch(
            "app.routers.junior_shared.store.update_project_thread_agent",
            return_value=launched,
        ) as changed:
            patched = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/agents/{run.id}",
                json={"status": "launched", "prompt": "Keep going"},
            )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["status"], "launched")
        self.assertEqual(changed.call_args.args[2], "storykeep")
        self.assertEqual(changed.call_args.args[3], thread_id)
        self.assertEqual(changed.call_args.args[4], run.id)
        self.assertEqual(changed.call_args.kwargs["status_value"], "launched")
        self.assertTrue(changed.call_args.kwargs["set_status"])

    def test_search_project_thread_requires_project_thread(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        with patch(
            "app.services.junior_shared_memory.project_thread_owned",
            side_effect=HTTPException(status_code=404, detail="Thread not found"),
        ):
            with self.assertRaises(HTTPException) as caught:
                store.search_project_thread(object(), owner, "storykeep", thread_id, "notes")
        self.assertEqual(caught.exception.status_code, 404)

    def test_search_project_thread_pages_that_thread(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        message_id = uuid.uuid4()
        hit = {"thread_id": thread_id, "message_id": message_id, "snippet": "notes"}
        with patch(
            "app.services.junior_shared_memory.project_thread_owned",
            return_value=SimpleNamespace(id=thread_id),
        ), patch(
            "app.services.junior_shared_memory.search_page",
            return_value=([hit], str(message_id)),
        ) as paged:
            rows, cursor = store.search_project_thread(
                object(),
                owner,
                "storykeep",
                thread_id,
                "notes",
                limit=1,
                cursor=message_id,
            )
        self.assertEqual(rows, [hit])
        self.assertEqual(cursor, str(message_id))
        self.assertEqual(paged.call_args.args[2], "notes")
        self.assertEqual(paged.call_args.kwargs["thread_id"], thread_id)
        self.assertEqual(paged.call_args.kwargs["limit"], 1)

    def test_project_thread_search_hit_owned_is_404_off_thread(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        message_id = uuid.uuid4()
        hit = {
            "thread_id": uuid.uuid4(),
            "message_id": message_id,
            "snippet": "other thread",
            "venue": "phone",
            "rank": 0.0,
        }
        with patch(
            "app.services.junior_shared_memory.project_thread_owned",
            return_value=SimpleNamespace(id=thread_id),
        ), patch("app.services.junior_shared_memory.search_hit_owned", return_value=hit):
            with self.assertRaises(HTTPException) as caught:
                store.project_thread_search_hit_owned(
                    object(), owner, "storykeep", thread_id, message_id
                )
        self.assertEqual(caught.exception.status_code, 404)

    def test_update_project_thread_search_hit_uses_thread_scope(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        message_id = uuid.uuid4()
        hit = {"thread_id": thread_id, "message_id": message_id, "snippet": "revised"}
        with patch(
            "app.services.junior_shared_memory.project_thread_search_hit_owned",
            return_value=hit,
        ), patch("app.services.junior_shared_memory.update_search_hit", return_value=hit) as updated:
            store.update_project_thread_search_hit(
                object(),
                owner,
                "storykeep",
                thread_id,
                message_id,
                snippet="revised",
                set_snippet=True,
            )
        self.assertEqual(updated.call_args.args[2], message_id)
        self.assertEqual(updated.call_args.kwargs["snippet"], "revised")
        self.assertTrue(updated.call_args.kwargs["set_snippet"])

    def test_project_thread_search_hit_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        message_id = uuid.uuid4()
        hit = {
            "thread_id": thread_id,
            "thread_title": "Notes",
            "message_id": message_id,
            "snippet": "pinned snippet",
            "venue": "phone",
            "created_at": now,
            "rank": 0.0,
        }
        app = _app()
        with patch(
            "app.routers.junior_shared.store.project_thread_search_hit_owned",
            return_value=hit,
        ) as loaded:
            one = TestClient(app).get(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/search/{message_id}"
            )
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["snippet"], "pinned snippet")
        self.assertEqual(str(one.json()["thread_id"]), str(thread_id))
        self.assertEqual(loaded.call_args.args[2], "storykeep")
        self.assertEqual(loaded.call_args.args[3], thread_id)
        self.assertEqual(loaded.call_args.args[4], message_id)

        revised = {**hit, "snippet": "revised snippet", "venue": "windows"}
        with patch(
            "app.routers.junior_shared.store.update_project_thread_search_hit",
            return_value=revised,
        ) as changed:
            posted = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/search/{message_id}",
                json={"snippet": "revised snippet", "venue": "windows"},
            )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()["snippet"], "revised snippet")
        self.assertEqual(changed.call_args.args[2], "storykeep")
        self.assertEqual(changed.call_args.args[3], thread_id)
        self.assertEqual(changed.call_args.args[4], message_id)
        self.assertEqual(changed.call_args.kwargs["snippet"], "revised snippet")
        self.assertEqual(changed.call_args.kwargs["venue"], "windows")
        self.assertTrue(changed.call_args.kwargs["set_snippet"])
        self.assertTrue(changed.call_args.kwargs["set_venue"])

    def test_project_thread_search_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        message_id = uuid.uuid4()
        hit = {
            "thread_id": thread_id,
            "thread_title": "Notes",
            "message_id": message_id,
            "snippet": "pinned snippet",
            "venue": "phone",
            "created_at": now,
            "rank": 0.4,
        }
        app = _app()
        with patch(
            "app.routers.junior_shared.store.search_project_thread",
            return_value=([hit], str(message_id)),
        ) as listed:
            page = TestClient(app).get(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/search",
                params={"q": "notes", "limit": 1, "cursor": str(message_id)},
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()[0]["snippet"], "pinned snippet")
        self.assertEqual(page.headers.get("x-next-cursor"), str(message_id))
        self.assertEqual(listed.call_args.args[2], "storykeep")
        self.assertEqual(listed.call_args.args[3], thread_id)
        self.assertEqual(listed.call_args.args[4], "notes")
        self.assertEqual(listed.call_args.kwargs["limit"], 1)

        with patch(
            "app.routers.junior_shared.store.search_project_thread",
            return_value=([hit], None),
        ) as ran:
            posted = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/search",
                json={"q": "notes"},
            )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()[0]["snippet"], "pinned snippet")
        self.assertEqual(ran.call_args.args[2], "storykeep")
        self.assertEqual(ran.call_args.args[3], thread_id)
        self.assertEqual(ran.call_args.args[4], "notes")

    def test_project_thread_agent_context_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        project = SimpleNamespace(
            id=uuid.uuid4(),
            slug="storykeep",
            display_name="StoryKeep",
            kind="app",
            repo_url=None,
            default_branch="main",
            notes=None,
            meta={},
            created_at=now,
            updated_at=now,
        )
        pack = {
            "project": project,
            "thread": None,
            "thread_summary": "pick up finance",
            "recent_messages": [],
            "memories": [],
            "search_hits": [],
            "launch_hint": "Start a Cursor agent on storykeep",
        }
        app = _app()
        with patch(
            "app.routers.junior_shared.store.project_thread_agent_context",
            return_value=pack,
        ) as loaded:
            got = TestClient(app).get(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/agent-context",
                params={"q": "finance"},
            )
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["project"]["slug"], "storykeep")
        self.assertEqual(got.json()["thread_summary"], "pick up finance")
        self.assertEqual(loaded.call_args.args[2], "storykeep")
        self.assertEqual(loaded.call_args.args[3], thread_id)
        self.assertEqual(loaded.call_args.kwargs["query"], "finance")

        with patch(
            "app.routers.junior_shared.store.update_project_thread_agent_context",
            return_value=pack,
        ) as pinned:
            posted = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/agent-context",
                json={"q": "finance"},
            )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()["project"]["slug"], "storykeep")
        self.assertEqual(pinned.call_args.args[2], "storykeep")
        self.assertEqual(pinned.call_args.args[3], thread_id)
        self.assertTrue(pinned.call_args.kwargs["set_query"])
        self.assertEqual(pinned.call_args.kwargs["query"], "finance")
        self.assertFalse(pinned.call_args.kwargs["set_thread_id"])

    def test_update_project_thread_agent_context_pins_path_thread(self):
        thread_id = uuid.uuid4()
        other = uuid.uuid4()
        with patch("app.services.junior_shared_memory.project_thread_owned", return_value=object()):
            with self.assertRaises(HTTPException) as caught:
                store.update_project_thread_agent_context(
                    object(),
                    object(),
                    "storykeep",
                    thread_id,
                    thread_id_value=other,
                    set_thread_id=True,
                )
        self.assertEqual(caught.exception.status_code, 404)

        with patch("app.services.junior_shared_memory.project_thread_owned", return_value=object()), patch(
            "app.services.junior_shared_memory.update_agent_context",
            return_value={"project": None},
        ) as pinned:
            store.update_project_thread_agent_context(
                object(),
                object(),
                "storykeep",
                thread_id,
                query="finance",
                set_query=True,
            )
        self.assertEqual(pinned.call_args.args[2], "storykeep")
        self.assertEqual(pinned.call_args.kwargs["thread_id"], thread_id)
        self.assertTrue(pinned.call_args.kwargs["set_thread_id"])
        self.assertTrue(pinned.call_args.kwargs["set_query"])
        self.assertEqual(pinned.call_args.kwargs["query"], "finance")

        with patch(
            "app.services.junior_shared_memory.project_thread_owned",
            side_effect=HTTPException(status_code=404, detail="Thread not found"),
        ):
            with self.assertRaises(HTTPException) as missing:
                store.project_thread_agent_context(object(), object(), "storykeep", thread_id)
        self.assertEqual(missing.exception.status_code, 404)

    def test_project_thread_memories_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        fact = SimpleNamespace(
            id=uuid.uuid4(),
            kind="note",
            content="Prefers short replies",
            source_thread=thread_id,
            created_at=now,
            updated_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.list_project_thread_memories_page",
            return_value=([fact], str(fact.id)),
        ) as listed:
            page = TestClient(app).get(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/memories",
                params={"limit": 1, "cursor": str(fact.id), "kind": "note"},
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()[0]["content"], "Prefers short replies")
        self.assertEqual(page.headers.get("x-next-cursor"), str(fact.id))
        self.assertEqual(listed.call_args.args[2], "storykeep")
        self.assertEqual(listed.call_args.args[3], thread_id)
        self.assertEqual(listed.call_args.kwargs["limit"], 1)
        self.assertEqual(listed.call_args.kwargs["kind"], "note")

        with patch(
            "app.routers.junior_shared.store.create_project_thread_memory",
            return_value=fact,
        ) as created:
            saved = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/memories",
                json={"content": "Prefers short replies", "kind": "note"},
            )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["source_thread"], str(thread_id))
        self.assertEqual(created.call_args.args[2], "storykeep")
        self.assertEqual(created.call_args.args[3], thread_id)
        self.assertEqual(created.call_args.kwargs["content"], "Prefers short replies")
        self.assertEqual(created.call_args.kwargs["kind"], "note")

    def test_project_thread_memory_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        memory = SimpleNamespace(
            id=uuid.uuid4(),
            kind="note",
            content="Prefers short replies",
            source_thread=thread_id,
            created_at=now,
            updated_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.project_thread_memory_owned",
            return_value=memory,
        ) as loaded:
            one = TestClient(app).get(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/memories/{memory.id}"
            )
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["content"], "Prefers short replies")
        self.assertEqual(loaded.call_args.args[2], "storykeep")
        self.assertEqual(loaded.call_args.args[3], thread_id)
        self.assertEqual(loaded.call_args.args[4], memory.id)

        revised = SimpleNamespace(
            id=memory.id,
            kind="note",
            content="revised fact",
            source_thread=thread_id,
            created_at=now,
            updated_at=now,
        )
        with patch(
            "app.routers.junior_shared.store.update_project_thread_memory",
            return_value=revised,
        ) as updated:
            posted = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/memories/{memory.id}",
                json={"content": "revised fact", "kind": "note", "source_thread": str(thread_id)},
            )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()["content"], "revised fact")
        self.assertEqual(updated.call_args.args[2], "storykeep")
        self.assertEqual(updated.call_args.args[3], thread_id)
        self.assertEqual(updated.call_args.args[4], memory.id)
        self.assertEqual(updated.call_args.kwargs["content"], "revised fact")
        self.assertTrue(updated.call_args.kwargs["set_kind"])
        self.assertEqual(updated.call_args.kwargs["kind"], "note")
        self.assertTrue(updated.call_args.kwargs["set_source_thread"])
        self.assertEqual(updated.call_args.kwargs["source_thread"], thread_id)

    def test_project_memory_owned_is_404_when_not_on_project(self):
        owner = _owner()
        memory_id = uuid.uuid4()
        other_thread = uuid.uuid4()
        db = MagicMock()
        db.get.return_value = SimpleNamespace(
            id=memory_id,
            user_id=owner.id,
            source_thread=other_thread,
            content="note",
            kind="note",
        )
        project = SimpleNamespace(slug="storykeep", meta={})
        with patch("app.services.junior_shared_memory.get_project", return_value=project), patch(
            "app.services.junior_shared_memory.project_search_thread_ids",
            return_value=[uuid.uuid4()],
        ):
            with self.assertRaises(HTTPException) as caught:
                store.project_memory_owned(db, owner, "storykeep", memory_id)
        self.assertEqual(caught.exception.status_code, 404)

    def test_project_search_hit_owned_is_404_when_not_on_project(self):
        owner = _owner()
        message_id = uuid.uuid4()
        other_thread = uuid.uuid4()
        message = SimpleNamespace(
            id=message_id,
            thread_id=other_thread,
            content="hi",
            venue="phone",
            created_at=None,
            meta={},
        )
        db = MagicMock()
        db.get.side_effect = [
            message,
            SimpleNamespace(id=other_thread, user_id=owner.id, title="other"),
        ]
        project = SimpleNamespace(slug="storykeep", meta={})
        with patch("app.services.junior_shared_memory.get_project", return_value=project), patch(
            "app.services.junior_shared_memory.project_search_thread_ids",
            return_value=[uuid.uuid4()],
        ):
            with self.assertRaises(HTTPException) as caught:
                store.project_search_hit_owned(db, owner, "storykeep", message_id)
        self.assertEqual(caught.exception.status_code, 404)

    def test_search_hit_owned_is_404_for_other_user(self):
        owner = _owner()
        other = uuid.uuid4()
        db = MagicMock()
        message = SimpleNamespace(id=uuid.uuid4(), thread_id=uuid.uuid4(), content="hi", venue="phone", created_at=None)
        db.get.side_effect = [message, SimpleNamespace(id=message.thread_id, user_id=other, title="x")]
        with self.assertRaises(HTTPException) as caught:
            store.search_hit_owned(db, owner, message.id)
        self.assertEqual(caught.exception.status_code, 404)

    def test_invalid_agent_status(self):
        with self.assertRaises(HTTPException) as caught:
            store.normalize_agent_status("explode")
        self.assertEqual(caught.exception.status_code, 400)

    def test_thread_session_owned_matches_venue(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        session_id = uuid.uuid4()
        thread = SimpleNamespace(id=thread_id, user_id=owner.id, venue_last="phone")
        session = SimpleNamespace(id=session_id, user_id=owner.id, venue="windows")
        db = MagicMock()
        db.get.side_effect = [thread, session]
        with self.assertRaises(HTTPException) as caught:
            store.thread_session_owned(db, owner, thread_id, session_id)
        self.assertEqual(caught.exception.status_code, 404)

        session.venue = "phone"
        db.get.side_effect = [thread, session]
        self.assertIs(store.thread_session_owned(db, owner, thread_id, session_id), session)

        db.get.side_effect = [None]
        with self.assertRaises(HTTPException) as missing:
            store.thread_session_owned(db, owner, thread_id, session_id)
        self.assertEqual(missing.exception.status_code, 404)

    def test_thread_session_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        session = SimpleNamespace(
            id=uuid.uuid4(),
            venue="phone",
            device_label="junior-mobile",
            last_seen_at=now,
            created_at=now,
        )
        app = _app()
        with patch("app.routers.junior_shared.store.thread_session_owned", return_value=session) as owned:
            got = TestClient(app).get(
                f"/api/v1/junior/threads/{thread_id}/sessions/{session.id}"
            )
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["venue"], "phone")
        self.assertEqual(got.json()["device_label"], "junior-mobile")
        self.assertEqual(owned.call_args.args[2], thread_id)
        self.assertEqual(owned.call_args.args[3], session.id)

        renamed = SimpleNamespace(
            id=session.id,
            venue="phone",
            device_label="junior-mobile-2",
            last_seen_at=now,
            created_at=now,
        )
        with patch(
            "app.routers.junior_shared.store.update_thread_session",
            return_value=renamed,
        ) as updated:
            posted = TestClient(app).post(
                f"/api/v1/junior/threads/{thread_id}/sessions/{session.id}",
                json={"device_label": "junior-mobile-2"},
            )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()["device_label"], "junior-mobile-2")
        self.assertEqual(updated.call_args.args[2], thread_id)
        self.assertEqual(updated.call_args.args[3], session.id)
        self.assertTrue(updated.call_args.kwargs["set_device_label"])
        self.assertEqual(updated.call_args.kwargs["device_label"], "junior-mobile-2")
        self.assertIsNone(updated.call_args.kwargs["venue"])

    def test_project_thread_session_owned_requires_project_thread_and_venue(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        session_id = uuid.uuid4()
        db = MagicMock()
        with patch.object(
            store,
            "project_thread_owned",
            side_effect=HTTPException(status_code=404, detail="Thread not found"),
        ):
            with self.assertRaises(HTTPException) as missing:
                store.project_thread_session_owned(db, owner, "storykeep", thread_id, session_id)
        self.assertEqual(missing.exception.status_code, 404)

        session = SimpleNamespace(id=session_id, venue="phone")
        with patch.object(store, "project_thread_owned", return_value=SimpleNamespace(id=thread_id)):
            with patch.object(store, "thread_session_owned", return_value=session) as owned:
                found = store.project_thread_session_owned(
                    db, owner, "storykeep", thread_id, session_id
                )
        self.assertIs(found, session)
        self.assertEqual(owned.call_args.args[2], thread_id)
        self.assertEqual(owned.call_args.args[3], session_id)

    def test_project_thread_session_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        session = SimpleNamespace(
            id=uuid.uuid4(),
            venue="phone",
            device_label="junior-mobile",
            last_seen_at=now,
            created_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.project_thread_session_owned",
            return_value=session,
        ) as owned:
            got = TestClient(app).get(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/sessions/{session.id}"
            )
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["venue"], "phone")
        self.assertEqual(owned.call_args.args[2], "storykeep")
        self.assertEqual(owned.call_args.args[3], thread_id)
        self.assertEqual(owned.call_args.args[4], session.id)

        renamed = SimpleNamespace(
            id=session.id,
            venue="phone",
            device_label="junior-mobile-2",
            last_seen_at=now,
            created_at=now,
        )
        with patch(
            "app.routers.junior_shared.store.update_project_thread_session",
            return_value=renamed,
        ) as updated:
            posted = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/sessions/{session.id}",
                json={"device_label": "junior-mobile-2"},
            )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()["device_label"], "junior-mobile-2")
        self.assertEqual(updated.call_args.args[2], "storykeep")
        self.assertEqual(updated.call_args.args[3], thread_id)
        self.assertEqual(updated.call_args.args[4], session.id)
        self.assertTrue(updated.call_args.kwargs["set_device_label"])
        self.assertEqual(updated.call_args.kwargs["device_label"], "junior-mobile-2")
        self.assertIsNone(updated.call_args.kwargs["venue"])

    def test_thread_sessions_page_uses_thread_venue(self):
        owner = _owner()
        thread = SimpleNamespace(id=uuid.uuid4(), venue_last="phone")
        db = MagicMock()
        with patch.object(store, "thread_owned", return_value=thread), patch.object(
            store, "list_sessions_page", return_value=([], None)
        ) as listed:
            rows, cursor = store.list_thread_sessions_page(
                db, owner, thread.id, limit=2, cursor="abc"
            )
        self.assertEqual(rows, [])
        self.assertIsNone(cursor)
        self.assertEqual(listed.call_args.kwargs["venue"], "phone")
        self.assertEqual(listed.call_args.kwargs["limit"], 2)

        with patch.object(
            store, "thread_owned", side_effect=HTTPException(status_code=404, detail="Thread not found")
        ):
            with self.assertRaises(HTTPException) as missing:
                store.list_thread_sessions_page(db, owner, thread.id)
        self.assertEqual(missing.exception.status_code, 404)

    def test_touch_thread_session_rejects_other_venue(self):
        owner = _owner()
        thread = SimpleNamespace(id=uuid.uuid4(), venue_last="phone")
        with patch.object(store, "thread_owned", return_value=thread), patch.object(
            store, "touch_session"
        ) as touched:
            with self.assertRaises(HTTPException) as caught:
                store.touch_thread_session(
                    MagicMock(), owner, thread.id, venue="windows", device_label="overlay"
                )
        self.assertEqual(caught.exception.status_code, 404)
        touched.assert_not_called()

        row = SimpleNamespace(id=uuid.uuid4())
        with patch.object(store, "thread_owned", return_value=thread), patch.object(
            store, "touch_session", return_value=row
        ) as touched:
            got = store.touch_thread_session(
                MagicMock(), owner, thread.id, venue=None, device_label="junior-mobile"
            )
        self.assertIs(got, row)
        self.assertEqual(touched.call_args.args[2], "phone")
        self.assertEqual(touched.call_args.args[3], "junior-mobile")

    def test_thread_sessions_page_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        session = SimpleNamespace(
            id=uuid.uuid4(),
            venue="phone",
            device_label="junior-mobile",
            last_seen_at=now,
            created_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.list_thread_sessions_page",
            return_value=([session], str(session.id)),
        ) as listed:
            page = TestClient(app).get(
                f"/api/v1/junior/threads/{thread_id}/sessions",
                params={"limit": 1, "cursor": str(session.id)},
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()[0]["venue"], "phone")
        self.assertEqual(page.headers.get("x-next-cursor"), str(session.id))
        self.assertEqual(listed.call_args.args[2], thread_id)
        self.assertEqual(listed.call_args.kwargs["limit"], 1)

        with patch(
            "app.routers.junior_shared.store.touch_thread_session",
            return_value=session,
        ) as touched:
            saved = TestClient(app).post(
                f"/api/v1/junior/threads/{thread_id}/sessions",
                json={"venue": "phone", "device_label": "junior-mobile"},
            )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["device_label"], "junior-mobile")
        self.assertEqual(touched.call_args.args[2], thread_id)
        self.assertEqual(touched.call_args.kwargs["venue"], "phone")
        self.assertEqual(touched.call_args.kwargs["device_label"], "junior-mobile")

    def test_project_session_owned_requires_project_venue(self):
        owner = _owner()
        session_id = uuid.uuid4()
        db = MagicMock()
        with patch.object(
            store,
            "get_project",
            side_effect=HTTPException(status_code=404, detail="Project not found"),
        ):
            with self.assertRaises(HTTPException) as missing:
                store.project_session_owned(db, owner, "missing", session_id)
        self.assertEqual(missing.exception.status_code, 404)

        project = SimpleNamespace(id=uuid.uuid4(), slug="storykeep", meta={})
        session = SimpleNamespace(id=session_id, venue="phone", user_id=owner.id)
        thread = SimpleNamespace(id=uuid.uuid4(), user_id=owner.id, venue_last="phone")
        with patch.object(store, "get_project", return_value=project), patch.object(
            store, "session_owned", return_value=session
        ), patch.object(store, "project_search_thread_ids", return_value=[thread.id]):
            db.get.return_value = thread
            found = store.project_session_owned(db, owner, "storykeep", session_id)
        self.assertIs(found, session)

        other = SimpleNamespace(id=thread.id, user_id=owner.id, venue_last="windows")
        with patch.object(store, "get_project", return_value=project), patch.object(
            store, "session_owned", return_value=session
        ), patch.object(store, "project_search_thread_ids", return_value=[thread.id]):
            db.get.return_value = other
            with self.assertRaises(HTTPException) as mismatch:
                store.project_session_owned(db, owner, "storykeep", session_id)
        self.assertEqual(mismatch.exception.status_code, 404)

    def test_project_session_routes(self):
        now = datetime.now(timezone.utc)
        session = SimpleNamespace(
            id=uuid.uuid4(),
            venue="phone",
            device_label="junior-mobile",
            last_seen_at=now,
            created_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.project_session_owned",
            return_value=session,
        ) as owned:
            got = TestClient(app).get(
                f"/api/v1/junior/projects/storykeep/sessions/{session.id}"
            )
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["venue"], "phone")
        self.assertEqual(owned.call_args.args[2], "storykeep")
        self.assertEqual(owned.call_args.args[3], session.id)

        renamed = SimpleNamespace(
            id=session.id,
            venue="phone",
            device_label="junior-mobile-2",
            last_seen_at=now,
            created_at=now,
        )
        with patch(
            "app.routers.junior_shared.store.update_project_session",
            return_value=renamed,
        ) as updated:
            posted = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/sessions/{session.id}",
                json={"device_label": "junior-mobile-2"},
            )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()["device_label"], "junior-mobile-2")
        self.assertEqual(updated.call_args.args[2], "storykeep")
        self.assertEqual(updated.call_args.args[3], session.id)
        self.assertTrue(updated.call_args.kwargs["set_device_label"])
        self.assertEqual(updated.call_args.kwargs["device_label"], "junior-mobile-2")
        self.assertIsNone(updated.call_args.kwargs["venue"])

    def test_project_thread_sessions_page_uses_project_thread(self):
        owner = _owner()
        thread = SimpleNamespace(id=uuid.uuid4(), venue_last="phone")
        db = MagicMock()
        with patch.object(store, "project_thread_owned", return_value=thread), patch.object(
            store, "list_thread_sessions_page", return_value=([], None)
        ) as listed:
            rows, cursor = store.list_project_thread_sessions_page(
                db, owner, "storykeep", thread.id, limit=2, cursor="abc"
            )
        self.assertEqual(rows, [])
        self.assertIsNone(cursor)
        self.assertEqual(listed.call_args.args[2], thread.id)
        self.assertEqual(listed.call_args.kwargs["limit"], 2)

        with patch.object(
            store,
            "project_thread_owned",
            side_effect=HTTPException(status_code=404, detail="Thread not found"),
        ):
            with self.assertRaises(HTTPException) as missing:
                store.list_project_thread_sessions_page(db, owner, "storykeep", thread.id)
        self.assertEqual(missing.exception.status_code, 404)

    def test_touch_project_thread_session_requires_project_thread(self):
        owner = _owner()
        thread = SimpleNamespace(id=uuid.uuid4(), venue_last="phone")
        row = SimpleNamespace(id=uuid.uuid4())
        with patch.object(store, "project_thread_owned", return_value=thread), patch.object(
            store, "touch_thread_session", return_value=row
        ) as touched:
            got = store.touch_project_thread_session(
                MagicMock(), owner, "storykeep", thread.id, venue="phone", device_label="junior-mobile"
            )
        self.assertIs(got, row)
        self.assertEqual(touched.call_args.args[2], thread.id)
        self.assertEqual(touched.call_args.kwargs["venue"], "phone")

        with patch.object(
            store,
            "project_thread_owned",
            side_effect=HTTPException(status_code=404, detail="Thread not found"),
        ), patch.object(store, "touch_thread_session") as touched:
            with self.assertRaises(HTTPException) as missing:
                store.touch_project_thread_session(
                    MagicMock(), owner, "missing", thread.id, venue="phone"
                )
        self.assertEqual(missing.exception.status_code, 404)
        touched.assert_not_called()

    def test_project_thread_sessions_page_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        session = SimpleNamespace(
            id=uuid.uuid4(),
            venue="phone",
            device_label="junior-mobile",
            last_seen_at=now,
            created_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.list_project_thread_sessions_page",
            return_value=([session], str(session.id)),
        ) as listed:
            page = TestClient(app).get(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/sessions",
                params={"limit": 1, "cursor": str(session.id)},
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()[0]["venue"], "phone")
        self.assertEqual(page.headers.get("x-next-cursor"), str(session.id))
        self.assertEqual(listed.call_args.args[2], "storykeep")
        self.assertEqual(listed.call_args.args[3], thread_id)
        self.assertEqual(listed.call_args.kwargs["limit"], 1)

        with patch(
            "app.routers.junior_shared.store.touch_project_thread_session",
            return_value=session,
        ) as touched:
            saved = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/threads/{thread_id}/sessions",
                json={"venue": "phone", "device_label": "junior-mobile"},
            )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["device_label"], "junior-mobile")
        self.assertEqual(touched.call_args.args[2], "storykeep")
        self.assertEqual(touched.call_args.args[3], thread_id)
        self.assertEqual(touched.call_args.kwargs["venue"], "phone")
        self.assertEqual(touched.call_args.kwargs["device_label"], "junior-mobile")

    def test_project_sessions_page_uses_project_venues(self):
        owner = _owner()
        project = SimpleNamespace(id=uuid.uuid4(), slug="storykeep")
        db = MagicMock()
        with patch.object(store, "get_project", return_value=project), patch.object(
            store, "project_session_venues", return_value={"phone"}
        ), patch.object(store, "list_sessions_page", return_value=([], None)) as listed:
            rows, cursor = store.list_project_sessions_page(
                db, owner, "storykeep", limit=2, cursor="abc"
            )
        self.assertEqual(rows, [])
        self.assertIsNone(cursor)
        self.assertEqual(listed.call_args.kwargs["venues"], {"phone"})
        self.assertEqual(listed.call_args.kwargs["limit"], 2)

        with patch.object(
            store,
            "get_project",
            side_effect=HTTPException(status_code=404, detail="Project not found"),
        ):
            with self.assertRaises(HTTPException) as missing:
                store.list_project_sessions_page(db, owner, "missing")
        self.assertEqual(missing.exception.status_code, 404)

    def test_touch_project_session_requires_project_venue(self):
        owner = _owner()
        project = SimpleNamespace(id=uuid.uuid4(), slug="storykeep")
        row = SimpleNamespace(id=uuid.uuid4())
        with patch.object(store, "get_project", return_value=project), patch.object(
            store, "project_session_venues", return_value={"phone"}
        ), patch.object(store, "touch_session", return_value=row) as touched:
            got = store.touch_project_session(
                MagicMock(), owner, "storykeep", venue="phone", device_label="junior-mobile"
            )
        self.assertIs(got, row)
        self.assertEqual(touched.call_args.args[2], "phone")
        self.assertEqual(touched.call_args.args[3], "junior-mobile")

        with patch.object(store, "get_project", return_value=project), patch.object(
            store, "project_session_venues", return_value={"windows"}
        ), patch.object(store, "touch_session") as touched:
            with self.assertRaises(HTTPException) as mismatch:
                store.touch_project_session(MagicMock(), owner, "storykeep", venue="phone")
        self.assertEqual(mismatch.exception.status_code, 404)
        touched.assert_not_called()

        with patch.object(
            store,
            "get_project",
            side_effect=HTTPException(status_code=404, detail="Project not found"),
        ), patch.object(store, "touch_session") as touched:
            with self.assertRaises(HTTPException) as missing:
                store.touch_project_session(MagicMock(), owner, "missing", venue="phone")
        self.assertEqual(missing.exception.status_code, 404)
        touched.assert_not_called()

    def test_project_sessions_page_routes(self):
        now = datetime.now(timezone.utc)
        session = SimpleNamespace(
            id=uuid.uuid4(),
            venue="phone",
            device_label="junior-mobile",
            last_seen_at=now,
            created_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.list_project_sessions_page",
            return_value=([session], str(session.id)),
        ) as listed:
            page = TestClient(app).get(
                "/api/v1/junior/projects/storykeep/sessions",
                params={"limit": 1, "cursor": str(session.id)},
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()[0]["venue"], "phone")
        self.assertEqual(page.headers.get("x-next-cursor"), str(session.id))
        self.assertEqual(listed.call_args.args[2], "storykeep")
        self.assertEqual(listed.call_args.kwargs["limit"], 1)

        with patch(
            "app.routers.junior_shared.store.touch_project_session",
            return_value=session,
        ) as touched:
            saved = TestClient(app).post(
                "/api/v1/junior/projects/storykeep/sessions",
                json={"venue": "phone", "device_label": "junior-mobile"},
            )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["device_label"], "junior-mobile")
        self.assertEqual(touched.call_args.args[2], "storykeep")
        self.assertEqual(touched.call_args.kwargs["venue"], "phone")
        self.assertEqual(touched.call_args.kwargs["device_label"], "junior-mobile")

    def test_session_owned_is_404_for_other_user(self):
        owner = _owner()
        other = uuid.uuid4()
        db = MagicMock()
        db.get.return_value = SimpleNamespace(id=uuid.uuid4(), user_id=other)
        with self.assertRaises(HTTPException) as caught:
            store.session_owned(db, owner, uuid.uuid4())
        self.assertEqual(caught.exception.status_code, 404)

    def test_reply_stub_without_key(self):
        owner = _owner()
        empty = store.TurnContext()
        with patch("app.services.junior_shared_memory.build_turn_context", return_value=empty):
            with patch("app.services.junior_shared_memory.settings") as settings:
                settings.xai_api_key = ""
                text, status = store.generate_junior_reply(MagicMock(), owner, SimpleNamespace(id=uuid.uuid4()))
        self.assertIsNone(text)
        self.assertEqual(status, "stubbed_no_key")

    def test_reply_calls_xai_when_key_set(self):
        owner = _owner()
        packed = store.TurnContext(xai_messages=[{"role": "user", "content": "hi"}])
        with patch("app.services.junior_shared_memory.build_turn_context", return_value=packed):
            with patch("app.services.junior_shared_memory.settings") as settings:
                settings.xai_api_key = "xai-not-a-real-key"
                with patch("app.services.junior_shared_memory.call_xai_complete", return_value={"text": "hello back"}):
                    text, status = store.generate_junior_reply(MagicMock(), owner, SimpleNamespace(id=uuid.uuid4()), "hi")
        self.assertEqual(text, "hello back")
        self.assertEqual(status, "ok")

    def test_xai_error_does_not_raise(self):
        owner = _owner()
        packed = store.TurnContext(xai_messages=[{"role": "user", "content": "hi"}])
        with patch("app.services.junior_shared_memory.build_turn_context", return_value=packed):
            with patch("app.services.junior_shared_memory.settings") as settings:
                settings.xai_api_key = "xai-not-a-real-key"
                with patch("app.services.junior_shared_memory.call_xai_complete", side_effect=HTTPException(status_code=502, detail="xAI down")):
                    text, status = store.generate_junior_reply(MagicMock(), owner, SimpleNamespace(id=uuid.uuid4()), "hi")
        self.assertIsNone(text)
        self.assertEqual(status, "xai_error")

    def test_resolve_thread_uses_last_open_or_creates(self):
        owner = _owner()
        existing = SimpleNamespace(id=uuid.uuid4(), user_id=owner.id, status="open")
        db = MagicMock()
        db.scalar.return_value = existing
        self.assertIs(store.resolve_thread(db, owner, None, "phone"), existing)
        created = SimpleNamespace(id=uuid.uuid4())
        db.scalar.return_value = None
        with patch("app.services.junior_shared_memory.create_thread", return_value=created) as make:
            self.assertIs(store.resolve_thread(db, owner, None, "voice"), created)
            make.assert_called_once()

    def test_remember_when_packs_search_hits(self):
        owner = _owner()
        thread = SimpleNamespace(id=uuid.uuid4(), summary="trailer quote")
        db = MagicMock()
        db.scalars.return_value = []
        hit = {"thread_title": "Finance", "snippet": "equipment finance"}
        with patch("app.services.junior_shared_memory.search", return_value=[hit]) as search:
            ctx = store.build_turn_context(db, owner, thread, "Remember when we did equipment finance?")
        search.assert_called_once()
        self.assertEqual(ctx.search_hits, [hit])
        self.assertTrue(any("Recall hits" in msg["content"] for msg in ctx.xai_messages if msg["role"] == "system"))
        self.assertTrue(store.wants_recall("Remember when the quote came in"))
        self.assertFalse(store.wants_recall("just a normal question"))

    def test_add_user_message_persists_without_junior_row(self):
        owner = _owner()
        thread_id = uuid.uuid4()
        thread = SimpleNamespace(
            id=thread_id,
            user_id=owner.id,
            title=None,
            venue_last="storykeep",
            updated_at=None,
        )
        db = MagicMock()
        db.get.return_value = thread
        db.scalar.return_value = None
        with patch("app.services.junior_shared_memory.generate_junior_reply", return_value=(None, "stubbed_no_key")):
            with patch("app.services.junior_shared_memory.maybe_refresh_summary"):
                user_row, junior_row, status = store.add_user_message(
                    db,
                    owner,
                    thread_id,
                    content="hello from overlay",
                    venue="windows",
                    meta={"screen": {"app": "Notepad"}},
                )
        self.assertEqual(user_row.role, "user")
        self.assertEqual(user_row.content, "hello from overlay")
        self.assertEqual(user_row.venue, "windows")
        self.assertIsNone(junior_row)
        self.assertEqual(status, "stubbed_no_key")
        self.assertEqual(thread.title, "hello from overlay")
        self.assertEqual(thread.venue_last, "windows")
        db.add.assert_called()

    def test_migration_reuses_users_and_has_fts(self):
        path = JUNIOR_SQL[0]
        sql = path.read_text(encoding="utf-8")
        self.assertIn("REFERENCES users(id)", sql)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS users", sql)
        for table in ("junior_threads", "junior_thread_messages", "junior_memories", "junior_sessions"):
            self.assertIn(table, sql)
        self.assertIn("content_tsv", sql)
        self.assertIn("title_tsv", sql)
        self.assertIn("to_tsvector", sql)
        self.assertIn("threads  → junior_threads", sql)
        projects_sql = JUNIOR_SQL[1].read_text(encoding="utf-8")
        self.assertIn("junior_projects", projects_sql)
        self.assertIn("junior_agent_runs", projects_sql)
        self.assertIn("REFERENCES users(id)", projects_sql)
        self.assertIn("kind IN ('app','api','overlay','infra','other')", projects_sql)

    def test_junior_sql_files_are_idempotent(self):
        for path in JUNIOR_SQL:
            raw = path.read_text(encoding="utf-8")
            _assert_idempotent_sql(self, raw, path)
            first = _sql_statements(raw)
            second = _sql_statements(raw)
            self.assertEqual(first, second, path)
            self.assertTrue(all(stmt.endswith(";") for stmt in first), path)

    def test_boot_applies_junior_sql_in_order(self):
        from app import main as app_main

        source = inspect.getsource(app_main._create_schema)
        memory_at = source.find('"001_junior_memory.sql"')
        projects_at = source.find('"002_junior_projects.sql"')
        self.assertGreater(memory_at, -1)
        self.assertGreater(projects_at, memory_at)
        self.assertIn("required=True", source)

    def test_container_includes_migrations_and_keeps_postgres_url(self):
        root_docker = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        backend_docker = (REPO_ROOT / "backend" / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("COPY backend/migrations ./migrations", root_docker)
        self.assertIn("COPY migrations ./migrations", backend_docker)
        railway = (REPO_ROOT / "docs" / "railway.md").read_text(encoding="utf-8")
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("DATABASE_URL=${{Postgres.DATABASE_URL}}", railway)
        self.assertIn("DATABASE_URL=${{Postgres.DATABASE_URL}}", readme)
        self.assertEqual(store.OWNER_EMAIL, "angry.tune8751@fastmail.com")

    def test_paginate_items_uses_before_id_and_limit(self):
        rows = [SimpleNamespace(id=uuid.uuid4()) for _ in range(5)]
        page, next_cursor = store.paginate_items(rows, limit=2)
        self.assertEqual(page, rows[:2])
        self.assertEqual(next_cursor, str(rows[1].id))
        page2, next2 = store.paginate_items(rows, limit=2, before_id=rows[1].id)
        self.assertEqual(page2, rows[2:4])
        self.assertEqual(next2, str(rows[3].id))
        last, done = store.paginate_items(rows, limit=2, cursor=rows[3].id)
        self.assertEqual(last, rows[4:])
        self.assertIsNone(done)

    def test_paginate_items_accepts_dict_message_ids(self):
        ids = [uuid.uuid4() for _ in range(3)]
        hits = [{"message_id": item, "snippet": str(i)} for i, item in enumerate(ids)]
        page, next_cursor = store.paginate_items(hits, limit=1, id_attr="message_id")
        self.assertEqual(page[0]["snippet"], "0")
        self.assertEqual(next_cursor, str(ids[0]))
        page2, done = store.paginate_items(hits, limit=2, cursor=ids[0], id_attr="message_id")
        self.assertEqual([hit["snippet"] for hit in page2], ["1", "2"])
        self.assertIsNone(done)

    def test_search_and_memories_routes_page(self):
        now = datetime.now(timezone.utc)
        message_id = uuid.uuid4()
        hit = {
            "thread_id": uuid.uuid4(),
            "thread_title": "Trailer",
            "message_id": message_id,
            "snippet": "remember the trailer",
            "venue": "phone",
            "created_at": now,
            "rank": 1.0,
        }
        memory = SimpleNamespace(
            id=uuid.uuid4(),
            kind="note",
            content="keep this",
            source_thread=None,
            created_at=now,
            updated_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.search_page",
            return_value=([hit], str(message_id)),
        ) as searched:
            response = TestClient(app).get(
                "/api/v1/junior/search",
                params={"q": "trailer", "limit": 1, "cursor": str(message_id)},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["snippet"], "remember the trailer")
        self.assertEqual(response.headers.get("x-next-cursor"), str(message_id))
        self.assertEqual(searched.call_args.kwargs["limit"], 1)

        with patch(
            "app.routers.junior_shared.store.list_memories_page",
            return_value=([memory], str(memory.id)),
        ) as listed:
            memories = TestClient(app).get(
                "/api/v1/junior/memories",
                params={"limit": 1, "before_id": str(memory.id)},
            )
        self.assertEqual(memories.status_code, 200)
        self.assertEqual(memories.json()[0]["content"], "keep this")
        self.assertEqual(memories.headers.get("x-next-cursor"), str(memory.id))
        self.assertEqual(listed.call_args.kwargs["limit"], 1)


class JuniorProjectAndAgentTests(unittest.TestCase):
    def test_list_and_upsert_projects(self):
        now = datetime.now(timezone.utc)
        row = SimpleNamespace(
            id=uuid.uuid4(),
            slug="storykeep",
            display_name="StoryKeep",
            kind="app",
            repo_url="https://cursor.com/codebase/steve-bitsko/Storykeep",
            default_branch="main",
            notes="Memory API lives here",
            meta={"venue": "storykeep"},
            created_at=now,
            updated_at=now,
        )
        app = _app()
        with patch("app.routers.junior_shared.store.list_projects_page", return_value=([row], None)):
            listed = TestClient(app).get("/api/v1/junior/projects")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["slug"], "storykeep")

        with patch(
            "app.routers.junior_shared.store.list_projects_page",
            return_value=([row], str(row.id)),
        ) as paged:
            page = TestClient(app).get(
                "/api/v1/junior/projects",
                params={"limit": 1, "cursor": str(row.id)},
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.headers.get("x-next-cursor"), str(row.id))
        self.assertEqual(paged.call_args.kwargs["limit"], 1)

        with patch("app.routers.junior_shared.store.upsert_project", return_value=row):
            saved = TestClient(app).post(
                "/api/v1/junior/projects",
                json={"slug": "storykeep", "display_name": "StoryKeep", "kind": "app"},
            )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["repo_url"], row.repo_url)

        renamed = SimpleNamespace(
            id=row.id,
            slug=row.slug,
            display_name="StoryKeep web",
            kind=row.kind,
            repo_url=row.repo_url,
            default_branch=row.default_branch,
            notes="Memory API lives here",
            meta=row.meta,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        with patch("app.routers.junior_shared.store.update_project", return_value=renamed) as updated:
            changed = TestClient(app).post(
                "/api/v1/junior/projects/storykeep",
                json={"slug": "storykeep", "display_name": "StoryKeep web", "notes": "Memory API lives here"},
            )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["display_name"], "StoryKeep web")
        self.assertEqual(updated.call_args.args[2], "storykeep")
        self.assertEqual(updated.call_args.kwargs["display_name"], "StoryKeep web")

        with patch("app.routers.junior_shared.store.get_project", return_value=row) as one_project:
            loaded = TestClient(app).get("/api/v1/junior/projects/storykeep")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json()["slug"], "storykeep")
        self.assertEqual(one_project.call_args.args[2], "storykeep")

    def test_agent_context_and_launch_stub(self):
        now = datetime.now(timezone.utc)
        project = SimpleNamespace(
            id=uuid.uuid4(),
            slug="storykeep",
            display_name="StoryKeep",
            kind="app",
            repo_url="https://cursor.com/codebase/steve-bitsko/Storykeep",
            default_branch="main",
            notes="Memory API",
            meta={},
            created_at=now,
            updated_at=now,
        )
        memory = SimpleNamespace(
            id=uuid.uuid4(),
            kind="decision",
            content="Railway Postgres is the source of truth",
            source_thread=None,
            created_at=now,
            updated_at=now,
        )
        msg = SimpleNamespace(
            id=uuid.uuid4(),
            thread_id=uuid.uuid4(),
            role="user",
            content="from the phone",
            venue="phone",
            meta={},
            created_at=now,
        )
        pack = {
            "project": project,
            "thread": None,
            "thread_summary": "pick up finance",
            "recent_messages": [msg],
            "memories": [memory],
            "search_hits": [],
            "launch_hint": "Start a Cursor agent on storykeep",
        }
        app = _app()
        with patch("app.routers.junior_shared.store.build_agent_context", return_value=pack):
            ctx = TestClient(app).get("/api/v1/junior/agent-context", params={"project": "storykeep", "q": "finance"})
        self.assertEqual(ctx.status_code, 200)
        body = ctx.json()
        self.assertEqual(body["project"]["slug"], "storykeep")
        self.assertEqual(body["thread_summary"], "pick up finance")
        self.assertEqual(body["recent_messages"][0]["venue"], "phone")
        self.assertIn("source of truth", body["memories"][0]["content"])
        self.assertIn("storykeep", body["launch_hint"])

        with patch("app.routers.junior_shared.store.build_agent_context", return_value=pack) as one_pack:
            one_ctx = TestClient(app).get("/api/v1/junior/agent-context/storykeep", params={"q": "finance"})
        self.assertEqual(one_ctx.status_code, 200)
        self.assertEqual(one_ctx.json()["project"]["slug"], "storykeep")
        self.assertEqual(one_pack.call_args.kwargs["project_slug"], "storykeep")
        self.assertEqual(one_pack.call_args.kwargs["query"], "finance")

        with patch("app.routers.junior_shared.store.update_agent_context", return_value=pack) as pinned:
            saved_ctx = TestClient(app).post(
                "/api/v1/junior/agent-context/storykeep",
                json={"q": "finance"},
            )
        self.assertEqual(saved_ctx.status_code, 200)
        self.assertEqual(saved_ctx.json()["project"]["slug"], "storykeep")
        self.assertEqual(pinned.call_args.args[2], "storykeep")
        self.assertEqual(pinned.call_args.kwargs["query"], "finance")
        self.assertTrue(pinned.call_args.kwargs["set_query"])

        run = SimpleNamespace(
            id=uuid.uuid4(),
            project_slug="storykeep",
            prompt="Fix the memory API",
            status="context_ready",
            cursor_agent_id=None,
            thread_id=None,
            created_at=now,
        )
        with patch("app.routers.junior_shared.store.record_agent_run", return_value=(run, pack)):
            launched = TestClient(app).post(
                "/api/v1/junior/agents",
                json={"project_slug": "storykeep", "prompt": "Fix the memory API"},
            )
        self.assertEqual(launched.status_code, 200)
        out = launched.json()
        self.assertEqual(out["run"]["status"], "context_ready")
        self.assertIsNone(out["run"]["cursor_agent_id"])
        self.assertFalse(out["called_cursor_api"])
        self.assertEqual(out["context"]["project"]["slug"], "storykeep")

        with patch(
            "app.routers.junior_shared.store.list_agent_runs_page",
            return_value=([run], str(run.id)),
        ) as listed:
            page = TestClient(app).get(
                "/api/v1/junior/agents",
                params={"limit": 1, "cursor": str(run.id), "project": "storykeep"},
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()[0]["status"], "context_ready")
        self.assertEqual(page.headers.get("x-next-cursor"), str(run.id))
        self.assertEqual(listed.call_args.kwargs["limit"], 1)
        self.assertEqual(listed.call_args.kwargs["project_slug"], "storykeep")

        with patch("app.routers.junior_shared.store.agent_run_owned", return_value=run) as owned:
            one = TestClient(app).get(f"/api/v1/junior/agents/{run.id}")
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["status"], "context_ready")
        self.assertEqual(str(owned.call_args.args[2]), str(run.id))

        launched_run = SimpleNamespace(
            id=run.id,
            project_slug="storykeep",
            prompt="Keep going",
            status="launched",
            cursor_agent_id="bc-test",
            thread_id=None,
            created_at=now,
        )
        with patch("app.routers.junior_shared.store.update_agent_run", return_value=launched_run) as updated:
            patched = TestClient(app).post(
                f"/api/v1/junior/agents/{run.id}",
                json={"prompt": "Keep going", "status": "launched", "cursor_agent_id": "bc-test"},
            )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["status"], "launched")
        self.assertEqual(patched.json()["cursor_agent_id"], "bc-test")
        self.assertEqual(str(updated.call_args.args[2]), str(run.id))
        self.assertEqual(updated.call_args.kwargs["status_value"], "launched")

        with patch(
            "app.routers.junior_shared.store.list_agent_runs_page",
            return_value=([run], str(run.id)),
        ) as project_page, patch("app.routers.junior_shared.store.get_project", return_value=project):
            scoped_page = TestClient(app).get(
                "/api/v1/junior/projects/storykeep/agents",
                params={"limit": 1, "cursor": str(run.id)},
            )
        self.assertEqual(scoped_page.status_code, 200)
        self.assertEqual(scoped_page.json()[0]["project_slug"], "storykeep")
        self.assertEqual(scoped_page.headers.get("x-next-cursor"), str(run.id))
        self.assertEqual(project_page.call_args.kwargs["project_slug"], "storykeep")
        self.assertEqual(project_page.call_args.kwargs["limit"], 1)

        with patch("app.routers.junior_shared.store.record_agent_run", return_value=(run, pack)) as recorded:
            scoped_launch = TestClient(app).post(
                "/api/v1/junior/projects/storykeep/agents",
                json={"prompt": "Fix the memory API"},
            )
        self.assertEqual(scoped_launch.status_code, 200)
        self.assertEqual(scoped_launch.json()["run"]["status"], "context_ready")
        self.assertFalse(scoped_launch.json()["called_cursor_api"])
        self.assertEqual(recorded.call_args.kwargs["project_slug"], "storykeep")
        self.assertEqual(recorded.call_args.kwargs["prompt"], "Fix the memory API")

        with patch("app.routers.junior_shared.store.project_agent_owned", return_value=run) as owned_project:
            scoped = TestClient(app).get(f"/api/v1/junior/projects/storykeep/agents/{run.id}")
        self.assertEqual(scoped.status_code, 200)
        self.assertEqual(scoped.json()["project_slug"], "storykeep")
        self.assertEqual(owned_project.call_args.args[2], "storykeep")
        self.assertEqual(str(owned_project.call_args.args[3]), str(run.id))

        with patch(
            "app.routers.junior_shared.store.update_project_agent", return_value=launched_run
        ) as project_run:
            changed = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/agents/{run.id}",
                json={"status": "launched", "prompt": "Keep going"},
            )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json()["status"], "launched")
        self.assertEqual(project_run.call_args.args[2], "storykeep")
        self.assertEqual(str(project_run.call_args.args[3]), str(run.id))
        self.assertEqual(project_run.call_args.kwargs["status_value"], "launched")

        thread_id = uuid.uuid4()
        threaded = SimpleNamespace(
            id=run.id,
            project_slug="storykeep",
            prompt="Fix the memory API",
            status="context_ready",
            cursor_agent_id=None,
            thread_id=thread_id,
            created_at=now,
        )
        with patch("app.routers.junior_shared.store.thread_agent_owned", return_value=threaded) as owned_thread:
            on_thread = TestClient(app).get(f"/api/v1/junior/threads/{thread_id}/agents/{run.id}")
        self.assertEqual(on_thread.status_code, 200)
        self.assertEqual(str(on_thread.json()["thread_id"]), str(thread_id))
        self.assertEqual(str(owned_thread.call_args.args[2]), str(thread_id))
        self.assertEqual(str(owned_thread.call_args.args[3]), str(run.id))

        moved = SimpleNamespace(
            id=run.id,
            project_slug="storykeep",
            prompt="Keep going",
            status="launched",
            cursor_agent_id="bc-thread",
            thread_id=thread_id,
            created_at=now,
        )
        with patch("app.routers.junior_shared.store.update_thread_agent", return_value=moved) as thread_run:
            thread_changed = TestClient(app).post(
                f"/api/v1/junior/threads/{thread_id}/agents/{run.id}",
                json={"status": "launched", "prompt": "Keep going"},
            )
        self.assertEqual(thread_changed.status_code, 200)
        self.assertEqual(thread_changed.json()["status"], "launched")
        self.assertEqual(str(thread_run.call_args.args[2]), str(thread_id))
        self.assertEqual(str(thread_run.call_args.args[3]), str(run.id))
        self.assertEqual(thread_run.call_args.kwargs["status_value"], "launched")

        with patch(
            "app.routers.junior_shared.store.list_agent_runs_page",
            return_value=([threaded], str(threaded.id)),
        ) as thread_page, patch("app.routers.junior_shared.store.thread_owned", return_value=object()):
            thread_list = TestClient(app).get(
                f"/api/v1/junior/threads/{thread_id}/agents",
                params={"limit": 1, "cursor": str(threaded.id)},
            )
        self.assertEqual(thread_list.status_code, 200)
        self.assertEqual(thread_list.json()[0]["project_slug"], "storykeep")
        self.assertEqual(thread_list.headers.get("x-next-cursor"), str(threaded.id))
        self.assertEqual(str(thread_page.call_args.kwargs["thread_id"]), str(thread_id))
        self.assertEqual(thread_page.call_args.kwargs["limit"], 1)

        with patch("app.routers.junior_shared.store.record_agent_run", return_value=(threaded, pack)) as recorded_thread, patch(
            "app.routers.junior_shared.store.thread_owned", return_value=object()
        ):
            thread_launch = TestClient(app).post(
                f"/api/v1/junior/threads/{thread_id}/agents",
                json={"prompt": "Fix the memory API", "project_slug": "storykeep"},
            )
        self.assertEqual(thread_launch.status_code, 200)
        self.assertEqual(thread_launch.json()["run"]["status"], "context_ready")
        self.assertFalse(thread_launch.json()["called_cursor_api"])
        self.assertEqual(recorded_thread.call_args.kwargs["project_slug"], "storykeep")
        self.assertEqual(recorded_thread.call_args.kwargs["prompt"], "Fix the memory API")
        self.assertEqual(str(recorded_thread.call_args.kwargs["thread_id"]), str(thread_id))

    def test_thread_search_hit_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        message_id = uuid.uuid4()
        hit = {
            "thread_id": thread_id,
            "thread_title": "Notes",
            "message_id": message_id,
            "snippet": "pinned snippet",
            "venue": "phone",
            "created_at": now,
            "rank": 0.0,
        }
        app = _app()
        with patch("app.routers.junior_shared.store.thread_search_hit_owned", return_value=hit) as owned:
            loaded = TestClient(app).get(f"/api/v1/junior/threads/{thread_id}/search/{message_id}")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json()["snippet"], "pinned snippet")
        self.assertEqual(str(owned.call_args.args[2]), str(thread_id))
        self.assertEqual(str(owned.call_args.args[3]), str(message_id))

        revised = {**hit, "snippet": "revised snippet"}
        with patch("app.routers.junior_shared.store.update_thread_search_hit", return_value=revised) as changed:
            posted = TestClient(app).post(
                f"/api/v1/junior/threads/{thread_id}/search/{message_id}",
                json={"snippet": "revised snippet"},
            )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()["snippet"], "revised snippet")
        self.assertEqual(str(changed.call_args.args[2]), str(thread_id))
        self.assertEqual(str(changed.call_args.args[3]), str(message_id))
        self.assertTrue(changed.call_args.kwargs["set_snippet"])
        self.assertEqual(changed.call_args.kwargs["snippet"], "revised snippet")

        with patch(
            "app.routers.junior_shared.store.search_page",
            return_value=([hit], str(message_id)),
        ) as paged, patch("app.routers.junior_shared.store.thread_owned", return_value=object()):
            listed = TestClient(app).get(
                f"/api/v1/junior/threads/{thread_id}/search",
                params={"q": "notes", "limit": 1, "cursor": str(message_id)},
            )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["snippet"], "pinned snippet")
        self.assertEqual(listed.headers.get("x-next-cursor"), str(message_id))
        self.assertEqual(paged.call_args.args[2], "notes")
        self.assertEqual(str(paged.call_args.kwargs["thread_id"]), str(thread_id))
        self.assertEqual(paged.call_args.kwargs["limit"], 1)

        with patch(
            "app.routers.junior_shared.store.search_page",
            return_value=([hit], None),
        ) as ran, patch("app.routers.junior_shared.store.thread_owned", return_value=object()):
            posted_search = TestClient(app).post(
                f"/api/v1/junior/threads/{thread_id}/search",
                json={"q": "notes"},
            )
        self.assertEqual(posted_search.status_code, 200)
        self.assertEqual(posted_search.json()[0]["snippet"], "pinned snippet")
        self.assertEqual(ran.call_args.args[2], "notes")
        self.assertEqual(str(ran.call_args.kwargs["thread_id"]), str(thread_id))

    def test_thread_agent_context_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        project = SimpleNamespace(
            id=uuid.uuid4(),
            slug="storykeep",
            display_name="StoryKeep",
            kind="app",
            repo_url=None,
            default_branch="main",
            notes=None,
            meta={},
            created_at=now,
            updated_at=now,
        )
        pack = {
            "project": project,
            "thread": None,
            "thread_summary": "pick up finance",
            "recent_messages": [],
            "memories": [],
            "search_hits": [],
            "launch_hint": "Start a Cursor agent on storykeep",
        }
        app = _app()
        with patch("app.routers.junior_shared.store.thread_agent_context", return_value=pack) as loaded:
            got = TestClient(app).get(
                f"/api/v1/junior/threads/{thread_id}/agent-context/storykeep",
                params={"q": "finance"},
            )
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["project"]["slug"], "storykeep")
        self.assertEqual(got.json()["thread_summary"], "pick up finance")
        self.assertEqual(str(loaded.call_args.args[2]), str(thread_id))
        self.assertEqual(loaded.call_args.args[3], "storykeep")
        self.assertEqual(loaded.call_args.kwargs["query"], "finance")

        with patch("app.routers.junior_shared.store.update_thread_agent_context", return_value=pack) as pinned:
            posted = TestClient(app).post(
                f"/api/v1/junior/threads/{thread_id}/agent-context/storykeep",
                json={"q": "finance"},
            )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()["project"]["slug"], "storykeep")
        self.assertEqual(str(pinned.call_args.args[2]), str(thread_id))
        self.assertEqual(pinned.call_args.args[3], "storykeep")
        self.assertTrue(pinned.call_args.kwargs["set_query"])
        self.assertEqual(pinned.call_args.kwargs["query"], "finance")
        self.assertFalse(pinned.call_args.kwargs["set_thread_id"])

    def test_update_thread_agent_context_pins_path_thread(self):
        thread_id = uuid.uuid4()
        other = uuid.uuid4()
        with patch("app.services.junior_shared_memory.thread_owned", return_value=object()):
            with self.assertRaises(HTTPException) as caught:
                store.update_thread_agent_context(
                    object(),
                    object(),
                    thread_id,
                    "storykeep",
                    thread_id_value=other,
                    set_thread_id=True,
                )
        self.assertEqual(caught.exception.status_code, 404)

        with patch("app.services.junior_shared_memory.thread_owned", return_value=object()), patch(
            "app.services.junior_shared_memory.update_agent_context",
            return_value={"project": None},
        ) as pinned:
            store.update_thread_agent_context(
                object(),
                object(),
                thread_id,
                "storykeep",
                query="finance",
                set_query=True,
            )
        self.assertEqual(pinned.call_args.args[2], "storykeep")
        self.assertEqual(pinned.call_args.kwargs["thread_id"], thread_id)
        self.assertTrue(pinned.call_args.kwargs["set_thread_id"])
        self.assertTrue(pinned.call_args.kwargs["set_query"])
        self.assertEqual(pinned.call_args.kwargs["query"], "finance")

    def test_project_search_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        message_id = uuid.uuid4()
        hit = {
            "thread_id": thread_id,
            "thread_title": "Notes",
            "message_id": message_id,
            "snippet": "pinned snippet",
            "venue": "phone",
            "created_at": now,
            "rank": 0.0,
        }
        app = _app()
        project = SimpleNamespace(slug="storykeep", meta={})
        with patch("app.routers.junior_shared.store.get_project", return_value=project), patch(
            "app.routers.junior_shared.store.project_search_thread_ids", return_value=[thread_id]
        ), patch(
            "app.routers.junior_shared.store.search_page",
            return_value=([hit], str(message_id)),
        ) as paged:
            listed = TestClient(app).get(
                "/api/v1/junior/projects/storykeep/search",
                params={"q": "notes", "limit": 1, "cursor": str(message_id)},
            )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["snippet"], "pinned snippet")
        self.assertEqual(listed.headers.get("x-next-cursor"), str(message_id))
        self.assertEqual(paged.call_args.args[2], "notes")
        self.assertEqual(paged.call_args.kwargs["thread_ids"], [thread_id])
        self.assertEqual(paged.call_args.kwargs["limit"], 1)

        with patch("app.routers.junior_shared.store.get_project", return_value=project), patch(
            "app.routers.junior_shared.store.project_search_thread_ids", return_value=[thread_id]
        ), patch(
            "app.routers.junior_shared.store.search_page",
            return_value=([hit], None),
        ) as ran:
            posted_search = TestClient(app).post(
                "/api/v1/junior/projects/storykeep/search",
                json={"q": "notes"},
            )
        self.assertEqual(posted_search.status_code, 200)
        self.assertEqual(posted_search.json()[0]["snippet"], "pinned snippet")
        self.assertEqual(ran.call_args.args[2], "notes")
        self.assertEqual(ran.call_args.kwargs["thread_ids"], [thread_id])

        with patch("app.routers.junior_shared.store.project_search_hit_owned", return_value=hit) as owned:
            loaded = TestClient(app).get(f"/api/v1/junior/projects/storykeep/search/{message_id}")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json()["snippet"], "pinned snippet")
        self.assertEqual(owned.call_args.args[2], "storykeep")
        self.assertEqual(str(owned.call_args.args[3]), str(message_id))

        revised = {**hit, "snippet": "revised snippet"}
        with patch("app.routers.junior_shared.store.update_project_search_hit", return_value=revised) as changed:
            posted = TestClient(app).post(
                f"/api/v1/junior/projects/storykeep/search/{message_id}",
                json={"snippet": "revised snippet"},
            )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()["snippet"], "revised snippet")
        self.assertEqual(changed.call_args.args[2], "storykeep")
        self.assertEqual(str(changed.call_args.args[3]), str(message_id))
        self.assertTrue(changed.call_args.kwargs["set_snippet"])
        self.assertEqual(changed.call_args.kwargs["snippet"], "revised snippet")

    def test_project_agent_context_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        project = SimpleNamespace(
            id=uuid.uuid4(),
            slug="storykeep",
            display_name="StoryKeep",
            kind="app",
            repo_url=None,
            default_branch="main",
            notes=None,
            meta={},
            created_at=now,
            updated_at=now,
        )
        pack = {
            "project": project,
            "thread": None,
            "thread_summary": "pick up finance",
            "recent_messages": [],
            "memories": [],
            "search_hits": [],
            "launch_hint": "Start a Cursor agent on storykeep",
        }
        app = _app()
        with patch("app.routers.junior_shared.store.project_agent_context", return_value=pack) as loaded:
            got = TestClient(app).get(
                "/api/v1/junior/projects/storykeep/agent-context",
                params={"q": "finance"},
            )
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["project"]["slug"], "storykeep")
        self.assertEqual(got.json()["thread_summary"], "pick up finance")
        self.assertEqual(loaded.call_args.args[2], "storykeep")
        self.assertEqual(loaded.call_args.kwargs["query"], "finance")

        with patch("app.routers.junior_shared.store.update_project_agent_context", return_value=pack) as pinned:
            posted = TestClient(app).post(
                "/api/v1/junior/projects/storykeep/agent-context",
                json={"q": "finance", "thread_id": str(thread_id)},
            )
        self.assertEqual(posted.status_code, 200)
        self.assertEqual(posted.json()["project"]["slug"], "storykeep")
        self.assertEqual(pinned.call_args.args[2], "storykeep")
        self.assertTrue(pinned.call_args.kwargs["set_query"])
        self.assertEqual(pinned.call_args.kwargs["query"], "finance")
        self.assertTrue(pinned.call_args.kwargs["set_thread_id"])
        self.assertEqual(str(pinned.call_args.kwargs["thread_id"]), str(thread_id))

    def test_project_memories_routes(self):
        now = datetime.now(timezone.utc)
        thread_id = uuid.uuid4()
        fact = SimpleNamespace(
            id=uuid.uuid4(),
            kind="note",
            content="Prefers short replies",
            source_thread=thread_id,
            created_at=now,
            updated_at=now,
        )
        app = _app()
        with patch(
            "app.routers.junior_shared.store.list_project_memories_page",
            return_value=([fact], str(fact.id)),
        ) as listed:
            page = TestClient(app).get(
                "/api/v1/junior/projects/storykeep/memories",
                params={"limit": 1, "cursor": str(fact.id), "kind": "note"},
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()[0]["content"], "Prefers short replies")
        self.assertEqual(page.headers.get("x-next-cursor"), str(fact.id))
        self.assertEqual(listed.call_args.args[2], "storykeep")
        self.assertEqual(listed.call_args.kwargs["limit"], 1)
        self.assertEqual(listed.call_args.kwargs["kind"], "note")

        with patch("app.routers.junior_shared.store.create_project_memory", return_value=fact) as created:
            saved = TestClient(app).post(
                "/api/v1/junior/projects/storykeep/memories",
                json={"content": "Prefers short replies", "kind": "note"},
            )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["source_thread"], str(thread_id))
        self.assertEqual(created.call_args.args[2], "storykeep")
        self.assertEqual(created.call_args.kwargs["content"], "Prefers short replies")
        self.assertEqual(created.call_args.kwargs["kind"], "note")

    def test_update_project_agent_context_uses_project_slug(self):
        thread_id = uuid.uuid4()
        with patch("app.services.junior_shared_memory.get_project", return_value=object()), patch(
            "app.services.junior_shared_memory.update_agent_context",
            return_value={"project": None},
        ) as pinned:
            store.update_project_agent_context(
                object(),
                object(),
                "storykeep",
                query="finance",
                thread_id=thread_id,
                set_query=True,
                set_thread_id=True,
            )
        self.assertEqual(pinned.call_args.args[2], "storykeep")
        self.assertEqual(pinned.call_args.kwargs["thread_id"], thread_id)
        self.assertTrue(pinned.call_args.kwargs["set_query"])
        self.assertTrue(pinned.call_args.kwargs["set_thread_id"])

        with patch(
            "app.services.junior_shared_memory.get_project",
            side_effect=HTTPException(status_code=404, detail="Project not found"),
        ):
            with self.assertRaises(HTTPException) as caught:
                store.project_agent_context(object(), object(), "missing")
        self.assertEqual(caught.exception.status_code, 404)

    def test_invalid_slug(self):
        with self.assertRaises(HTTPException) as caught:
            store.normalize_slug("Story Keep")
        self.assertEqual(caught.exception.status_code, 400)

    def test_list_and_touch_sessions(self):
        now = datetime.now(timezone.utc)
        row = SimpleNamespace(
            id=uuid.uuid4(),
            venue="phone",
            device_label="junior-mobile",
            last_seen_at=now,
            created_at=now,
        )
        app = _app()
        with patch("app.routers.junior_shared.store.list_sessions_page", return_value=([row], None)):
            listed = TestClient(app).get("/api/v1/junior/sessions")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["venue"], "phone")

        with patch(
            "app.routers.junior_shared.store.list_sessions_page",
            return_value=([row], str(row.id)),
        ) as paged:
            page = TestClient(app).get(
                "/api/v1/junior/sessions",
                params={"limit": 1, "cursor": str(row.id), "venue": "phone"},
            )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.headers.get("x-next-cursor"), str(row.id))
        self.assertEqual(paged.call_args.kwargs["limit"], 1)
        self.assertEqual(paged.call_args.kwargs["venue"], "phone")

        with patch("app.routers.junior_shared.store.touch_session", return_value=row) as touched:
            saved = TestClient(app).post(
                "/api/v1/junior/sessions",
                json={"venue": "phone", "device_label": "junior-mobile"},
            )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["device_label"], "junior-mobile")
        self.assertEqual(touched.call_args.args[2], "phone")

        with patch("app.routers.junior_shared.store.session_owned", return_value=row) as owned:
            one = TestClient(app).get(f"/api/v1/junior/sessions/{row.id}")
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["device_label"], "junior-mobile")
        self.assertEqual(str(owned.call_args.args[2]), str(row.id))

        renamed = SimpleNamespace(
            id=row.id,
            venue="phone",
            device_label="junior-mobile-2",
            last_seen_at=now,
            created_at=now,
        )
        with patch("app.routers.junior_shared.store.update_session", return_value=renamed) as updated:
            patched = TestClient(app).post(
                f"/api/v1/junior/sessions/{row.id}",
                json={"device_label": "junior-mobile-2"},
            )
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["device_label"], "junior-mobile-2")
        self.assertEqual(str(updated.call_args.args[2]), str(row.id))
        self.assertEqual(updated.call_args.kwargs["device_label"], "junior-mobile-2")

    def test_seed_writes_projects_and_decisions(self):
        owner = _owner()
        owner.email = store.OWNER_EMAIL
        self.assertEqual(owner.email, "angry.tune8751@fastmail.com")
        db = MagicMock()
        db.scalar.side_effect = [owner] + [None] * 20
        store.seed_owner_projects_and_decisions(db)
        added = [call.args[0] for call in db.add.call_args_list]
        slugs = {getattr(item, "slug", None) for item in added}
        self.assertEqual({"storykeep", "junior-phone", "windows-overlay"}, slugs & {"storykeep", "junior-phone", "windows-overlay"})
        by_slug = {item["slug"]: item for item in store.SEED_PROJECTS}
        self.assertEqual(set(by_slug), {"storykeep", "junior-phone", "windows-overlay"})
        self.assertEqual(by_slug["storykeep"]["display_name"], "StoryKeep")
        self.assertEqual(by_slug["junior-phone"]["display_name"], "Junior mobile")
        self.assertEqual(by_slug["junior-phone"]["repo_url"], "https://cursor.com/codebase/steve-bitsko/junior-mobile")
        self.assertEqual(by_slug["junior-phone"]["meta"].get("stack"), "expo")
        self.assertEqual(by_slug["windows-overlay"]["display_name"], "Windows overlay")
        phone_row = next(item for item in added if getattr(item, "slug", None) == "junior-phone")
        self.assertEqual(phone_row.display_name, "Junior mobile")
        self.assertEqual(phone_row.repo_url, "https://cursor.com/codebase/steve-bitsko/junior-mobile")
        storykeep_row = next(item for item in added if getattr(item, "slug", None) == "storykeep")
        overlay_row = next(item for item in added if getattr(item, "slug", None) == "windows-overlay")
        self.assertEqual(storykeep_row.slug, "storykeep")
        self.assertEqual(overlay_row.slug, "windows-overlay")
        decisions = [item.content for item in added if getattr(item, "kind", None) == "decision"]
        self.assertTrue(any("Railway Postgres" in text for text in decisions))
        self.assertTrue(any("venue=phone" in text for text in decisions))


if __name__ == "__main__":
    unittest.main()
