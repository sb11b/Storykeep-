from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import get_db
from app.deps import get_current_user
from app.main import http_exception_with_message, request_validation_handler
from app.routers import overlay as overlay_router
from app.routers.auth import get_me, patch_me
from app.schemas import ProfileOut


def _app(user=None):
    app = FastAPI()
    app.add_exception_handler(StarletteHTTPException, http_exception_with_message)
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.include_router(overlay_router.router, prefix="/api/v1")
    app.add_api_route("/api/v1/me", get_me, methods=["GET"], response_model=ProfileOut)
    app.add_api_route("/api/v1/me", patch_me, methods=["PATCH"], response_model=ProfileOut)
    owner = user or SimpleNamespace(
        id=uuid4(),
        email="reader@example.com",
        display_name="Steve",
        avatar_media_id=None,
        avatar_url=None,
        birthdate=None,
        preferences={},
        profile_read_only=False,
        created_at="2026-01-01T00:00:00Z",
        totp_enabled=False,
        email_otp_enabled=False,
        totp_secret_encrypted=None,
        backup_code_hashes=[],
        is_demo_locked=False,
    )
    db = MagicMock()

    def fake_db():
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_user] = lambda: owner
    return app, db, owner


class ProfileUuidRouteTests(unittest.TestCase):
    def test_media_refresh_path_is_invalid_id(self):
        app, _db, _owner = _app()
        client = TestClient(app)
        response = client.get("/api/v1/media/refresh")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Invalid id")
        self.assertNotIn("found `r`", response.text)
        self.assertNotIn("valid UUID", response.text)
        self.assertNotIn("pydantic", response.text.lower())

    def test_media_profile_path_is_invalid_id(self):
        app, _db, _owner = _app()
        client = TestClient(app)
        response = client.get("/api/v1/media/profile")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Invalid id")
        self.assertNotIn("found `p`", response.text)

    def test_patch_me_refresh_avatar_is_invalid_id(self):
        app, _db, _owner = _app()
        client = TestClient(app)
        response = client.patch("/api/v1/me", json={"avatar_media_id": "refresh"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["detail"], "Invalid id")
        self.assertNotIn("found `r`", response.text)
        self.assertNotIn("valid UUID", response.text)


if __name__ == "__main__":
    unittest.main()
