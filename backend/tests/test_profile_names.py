from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.deps import get_current_user
from app.routers.auth import patch_profile
from app.schemas import ProfileOut


def _app(user=None):
    app = FastAPI()
    app.add_api_route("/api/v1/auth/profile", patch_profile, methods=["PATCH"], response_model=ProfileOut)
    owner = user or SimpleNamespace(
        id=uuid4(),
        email="reader@example.com",
        display_name="Steve",
        legal_name="Steven Bitsko",
        school_name="Steve B.",
        avatar_media_id=None,
        birthdate=None,
        preferences={},
        profile_read_only=False,
        created_at="2026-01-01T00:00:00Z",
        totp_enabled=False,
        email_otp_enabled=False,
        totp_secret_encrypted=None,
        backup_code_hashes=[],
        is_demo_locked=False,
        updated_at="2026-01-01T00:00:00Z",
    )
    db = MagicMock()

    def fake_db():
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_user] = lambda: owner
    return app, db, owner


class ProfileNamePatchTests(unittest.TestCase):
    def test_patch_birthdate_does_not_clear_display_name(self):
        app, _db, owner = _app()
        client = TestClient(app)
        response = client.patch("/api/v1/auth/profile", json={"birthdate": "2010-05-01"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(owner.display_name, "Steve")
        self.assertEqual(owner.legal_name, "Steven Bitsko")
        self.assertEqual(owner.school_name, "Steve B.")

    def test_patch_legal_name_only(self):
        app, _db, owner = _app()
        client = TestClient(app)
        response = client.patch("/api/v1/auth/profile", json={"legal_name": "Steven A. Bitsko"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(owner.display_name, "Steve")
        self.assertEqual(owner.legal_name, "Steven A. Bitsko")
        self.assertEqual(owner.school_name, "Steve B.")


if __name__ == "__main__":
    unittest.main()
