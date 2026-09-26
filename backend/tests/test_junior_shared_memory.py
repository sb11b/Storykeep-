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
        ):
            response = client.get(path)
            self.assertEqual(response.status_code, 401, path)
        self.assertEqual(client.post("/api/v1/junior/messages", json={"text": "hi", "venue": "phone"}).status_code, 401)
        self.assertEqual(client.post("/api/v1/junior/agents", json={"project_slug": "storykeep", "prompt": "go"}).status_code, 401)

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
            ("POST", "/api/v1/junior/messages"),
            ("POST", "/api/v1/junior/agents"),
        ):
            response = client.request(method, path, json={"text": "hi", "venue": "phone", "project_slug": "storykeep", "prompt": "go"})
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
            "app.routers.junior_shared.store.list_messages", return_value=[user_msg]
        ):
            resumed = TestClient(app).post(f"/api/v1/junior/threads/{thread_id}/continue", json={})
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.json()["thread"]["id"], str(thread_id))
        self.assertEqual(len(resumed.json()["messages"]), 1)

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
        with patch("app.routers.junior_shared.store.list_projects", return_value=[row]):
            listed = TestClient(app).get("/api/v1/junior/projects")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()[0]["slug"], "storykeep")

        with patch("app.routers.junior_shared.store.upsert_project", return_value=row):
            saved = TestClient(app).post(
                "/api/v1/junior/projects",
                json={"slug": "storykeep", "display_name": "StoryKeep", "kind": "app"},
            )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["repo_url"], row.repo_url)

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

    def test_invalid_slug(self):
        with self.assertRaises(HTTPException) as caught:
            store.normalize_slug("Story Keep")
        self.assertEqual(caught.exception.status_code, 400)

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
