from __future__ import annotations

import inspect
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from fastapi import HTTPException

from app.deps import get_current_user, require_user
from app.routers import auth as auth_router
from app.routers import junior_chats as chats_router
from app.routers import junior_shared as shared_router
from app.services.demo_lock import reject_authentication


class RequireUserTests(unittest.TestCase):
    def test_demo_user_rejected(self):
        demo = SimpleNamespace(id=uuid.uuid4(), email="steve@storykeep.local", is_demo_locked=True)
        with self.assertRaises(HTTPException) as ctx:
            require_user(demo)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_owner_passes(self):
        owner = SimpleNamespace(id=uuid.uuid4(), email="stevebitsko@duck.com", is_demo_locked=False)
        self.assertIs(require_user(owner), owner)


class SessionCookieTests(unittest.TestCase):
    def test_cookie_flags_in_auth_router(self):
        source = inspect.getsource(auth_router._set_cookie)
        self.assertIn("httponly=True", source)
        self.assertIn('samesite="lax"', source)
        self.assertIn("secure=settings.cookie_secure", source)


class JuniorChatsLockdownTests(unittest.TestCase):
    def test_demo_gets_403_not_empty_list(self):
        app = FastAPI()
        app.include_router(chats_router.router, prefix="/api/v1")
        demo = SimpleNamespace(id=uuid.uuid4(), email="steve@storykeep.local", is_demo_locked=True)

        def fake_db():
            yield MagicMock()

        app.dependency_overrides[get_db] = fake_db
        app.dependency_overrides[get_current_user] = lambda: demo
        client = TestClient(app)
        response = client.get("/api/v1/junior/chats")
        self.assertEqual(response.status_code, 403)


class JuniorSharedLockdownTests(unittest.TestCase):
    def test_demo_cannot_list_shared_threads(self):
        app = FastAPI()
        app.include_router(shared_router.router, prefix="/api/v1")
        demo = SimpleNamespace(id=uuid.uuid4(), email="steve@storykeep.local", is_demo_locked=True)

        def fake_db():
            yield MagicMock()

        app.dependency_overrides[get_db] = fake_db
        app.dependency_overrides[get_current_user] = lambda: demo
        client = TestClient(app)
        for path in (
            "/api/v1/junior/threads",
            "/api/v1/junior/messages",
            "/api/v1/junior/search?q=hello",
            "/api/v1/junior/memories",
            "/api/v1/junior/projects",
            "/api/v1/junior/agent-context?project=storykeep",
            "/api/v1/junior/agents",
        ):
            response = client.get(path)
            self.assertEqual(response.status_code, 403, path)


class LoggingLockdownTests(unittest.TestCase):
    def test_request_logging_never_logs_body(self):
        from app import request_logging

        source = inspect.getsource(request_logging.JuniorRequestLogMiddleware)
        self.assertIn("latency_ms", source)
        self.assertIn("user_id=", source)
        self.assertNotIn("logger.info(body", source.lower())
        self.assertNotIn("headers.get", source.lower())

    def test_log_model_call_metadata_only(self):
        from app.http_limits import log_model_call

        source = inspect.getsource(log_model_call)
        self.assertIn("user_id=", source)
        self.assertIn("message_id=", source)
        self.assertNotIn("content", source)


class SttSocketAuthTests(unittest.TestCase):
    def test_socket_rejects_closed_demo(self):
        from app.routers import stt as stt_router

        source = inspect.getsource(stt_router._user_from_socket)
        self.assertIn("reject_authentication", source)


if __name__ == "__main__":
    unittest.main()
