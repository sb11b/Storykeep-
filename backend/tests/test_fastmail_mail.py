from __future__ import annotations

import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.http_limits import redact_secrets
from app.main import http_exception_with_message
from app.routers import mail as mail_router
from app.services import fastmail_jmap as jmap
from app.services import mail as mail_service
from app.services import mail_tool

SESSION = {
    "username": "steve@fastmail.com",
    "apiUrl": "https://api.fastmail.com/jmap/api/",
    "primaryAccounts": {
        "urn:ietf:params:jmap:core": "u1",
        "urn:ietf:params:jmap:mail": "u1",
        "urn:ietf:params:jmap:submission": "u1",
    },
    "accounts": {"u1": {"name": "Steve"}},
}

MAILBOXES = [
    {"id": "mb-inbox", "name": "Inbox", "role": "inbox", "unreadEmails": 2},
    {"id": "mb-sent", "name": "Sent", "role": "sent", "unreadEmails": 0},
    {"id": "mb-drafts", "name": "Drafts", "role": "drafts", "unreadEmails": 0},
]

EMAILS = [
    {
        "id": "e1",
        "from": [{"name": "Ada", "email": "ada@example.com"}],
        "to": [{"email": "steve@fastmail.com"}],
        "subject": "Hello there",
        "receivedAt": "2026-09-15T12:00:00Z",
        "preview": "Hi Steve",
        "keywords": {},
        "hasAttachment": False,
        "textBody": [{"partId": "t", "type": "text/plain"}],
        "htmlBody": [],
        "bodyValues": {"t": {"value": "Hi Steve, this is the body."}},
    }
]


def _jmap_handler(request: httpx.Request) -> httpx.Response:
    auth = request.headers.get("authorization") or ""
    if b"fmu1-" in (request.content or b"") or "fmu1-" in str(request.url):
        raise AssertionError("token leaked into URL or JSON body")
    if request.url.path.endswith("/jmap/session"):
        if not auth.startswith("Bearer "):
            return httpx.Response(401, json={"detail": "no"})
        return httpx.Response(200, json=SESSION)
    payload = json.loads(request.content.decode())
    calls = payload.get("methodCalls") or []
    responses = []
    created_draft = False
    for name, args, call_id in calls:
        if name == "Mailbox/get":
            responses.append(["Mailbox/get", {"list": MAILBOXES}, call_id])
        elif name == "Email/query":
            assert args.get("limit") <= 50
            ids = [row["id"] for row in EMAILS]
            if args.get("filter", {}).get("notKeyword") == "$seen":
                ids = [row["id"] for row in EMAILS if "$seen" not in (row.get("keywords") or {})]
            responses.append(["Email/query", {"ids": ids, "total": len(ids)}, call_id])
        elif name == "Email/get":
            ids = args.get("ids")
            if ids is None and args.get("#ids"):
                ids = [row["id"] for row in EMAILS]
            listed = [row for row in EMAILS if row["id"] in ids]
            responses.append(["Email/get", {"list": listed}, call_id])
        elif name == "Identity/get":
            responses.append(
                ["Identity/get", {"list": [{"id": "id1", "email": "steve@fastmail.com", "name": "Steve"}]}, call_id]
            )
        elif name == "Email/set":
            created_draft = True
            responses.append(["Email/set", {"created": {"draft": {"id": "draft-1"}}}, call_id])
        elif name == "EmailSubmission/set":
            assert created_draft
            responses.append(
                ["EmailSubmission/set", {"created": {"send": {"id": "sub-1", "emailId": "sent-1"}}}, call_id]
            )
        else:
            responses.append(["error", {"type": "unknownMethod", "description": name}, call_id])
    return httpx.Response(200, json={"methodResponses": responses})


_RealClient = httpx.Client


class FakeClient:
    def __init__(self, *args, **kwargs):
        self._client = _RealClient(transport=httpx.MockTransport(_jmap_handler))

    def __enter__(self):
        return self._client

    def __exit__(self, *args):
        self._client.close()


def _app(user: SimpleNamespace) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(StarletteHTTPException, http_exception_with_message)
    app.include_router(mail_router.router, prefix="/api/v1")

    def fake_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_user] = lambda: user
    return app


class FastmailJmapTests(unittest.TestCase):
    def setUp(self):
        jmap._session_cache.clear()
        self._prev = settings.fastmail_token
        settings.fastmail_token = "fmu1-test-token-not-real"

    def tearDown(self):
        settings.fastmail_token = self._prev
        jmap._session_cache.clear()

    def test_list_inbox_from_subject_date_unseen(self):
        with patch("app.services.fastmail_jmap.httpx.Client", FakeClient):
            listed = jmap.list_emails("fmu1-test-token-not-real", role="inbox", limit=50)
        self.assertEqual(listed["mailbox"]["role"], "inbox")
        self.assertEqual(listed["items"][0]["from"], "Ada <ada@example.com>")
        self.assertEqual(listed["items"][0]["subject"], "Hello there")
        self.assertTrue(listed["items"][0]["unseen"])
        self.assertEqual(listed["limit"], 50)
        roles = {box["role"] for box in listed["mailboxes"]}
        self.assertTrue({"inbox", "sent", "drafts"} <= roles)

    def test_limit_is_capped(self):
        self.assertEqual(jmap.clamp_limit(5000), 50)
        self.assertEqual(jmap.clamp_limit(0), 1)

    def test_open_body(self):
        with patch("app.services.fastmail_jmap.httpx.Client", FakeClient):
            row = jmap.get_email("fmu1-test-token-not-real", "e1")
        self.assertIn("Hi Steve, this is the body.", row["body"])

    def test_send(self):
        with patch("app.services.fastmail_jmap.httpx.Client", FakeClient):
            result = jmap.send_email(
                "fmu1-test-token-not-real",
                to="steve@fastmail.com",
                subject="Ping",
                body="hello from StoryKeep",
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["to"], "steve@fastmail.com")

    def test_missing_session_is_connect_fastmail(self):
        def boom(*_a, **_k):
            return httpx.Response(401, text="nope")

        class FailClient:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return SimpleNamespace(get=lambda *a, **k: boom())

            def __exit__(self, *a):
                return False

        with patch("app.services.fastmail_jmap.httpx.Client", FailClient):
            with self.assertRaises(HTTPException) as raised:
                jmap.fetch_session("fmu1-test-token-not-real")
        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.detail, "Connect Fastmail")


class MailAccessTests(unittest.TestCase):
    def setUp(self):
        self._prev = settings.fastmail_token
        settings.fastmail_token = ""

    def tearDown(self):
        settings.fastmail_token = self._prev

    def test_demo_forbidden(self):
        settings.fastmail_token = "fmu1-test-token-not-real"
        user = SimpleNamespace(id=uuid.uuid4(), email="steve@storykeep.local", is_demo_locked=True)
        client = TestClient(_app(user))
        response = client.get("/api/v1/mail/messages")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Mail is not enabled on this account")
        self.assertNotIn("owner account", response.json()["detail"])
        self.assertNotEqual(response.status_code, 500)

    def test_live_login_without_credentials_is_401_connect(self):
        user = SimpleNamespace(id=uuid.uuid4(), email="other@example.com", is_demo_locked=False)
        db = MagicMock()
        db.get.return_value = None

        def fake_db():
            yield db

        app = _app(user)
        app.dependency_overrides[get_db] = fake_db
        client = TestClient(app)
        response = client.get("/api/v1/mail/messages")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Connect Fastmail")

    def test_env_token_opens_mail_without_owner_email(self):
        settings.fastmail_token = "fmu1-test-token-not-real"
        user = SimpleNamespace(id=uuid.uuid4(), email="steve-login@example.com", is_demo_locked=False)
        db = MagicMock()
        db.get.return_value = None

        def fake_db():
            yield db

        app = _app(user)
        app.dependency_overrides[get_db] = fake_db
        with patch("app.services.fastmail_jmap.httpx.Client", FakeClient):
            client = TestClient(app)
            response = client.get("/api/v1/mail/messages")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mailbox"]["role"], "inbox")
        self.assertTrue(response.json()["items"])

    def test_stored_mail_token_opens_inbox_without_env(self):
        settings.fastmail_token = ""
        user = SimpleNamespace(id=uuid.uuid4(), email="other@example.com", is_demo_locked=False)
        with (
            patch("app.services.mail.stored_mail_token", return_value="fmu1-test-token-not-real"),
            patch("app.services.mail.stored_app_password", return_value=""),
            patch("app.services.fastmail_jmap.httpx.Client", FakeClient),
        ):
            client = TestClient(_app(user))
            response = client.get("/api/v1/mail/messages")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mailbox"]["role"], "inbox")

    def test_disconnect_clears_stored_fastmail_not_session(self):
        user = SimpleNamespace(id=uuid.uuid4(), email="steve-login@example.com", is_demo_locked=False)
        mail_row = object()
        cal_row = object()
        db = MagicMock()

        def fake_get(model, _id):
            if model is mail_service.FastmailMailAccount:
                return mail_row
            if model is mail_service.FastmailCalendarAccount:
                return cal_row
            return None

        db.get.side_effect = fake_get
        mail_service.disconnect(db, user)
        db.delete.assert_any_call(mail_row)
        db.delete.assert_any_call(cal_row)
        db.flush.assert_called()

    def test_send_requires_confirm(self):
        settings.fastmail_token = "fmu1-test-token-not-real"
        user = SimpleNamespace(id=uuid.uuid4(), email="steve-login@example.com", is_demo_locked=False)
        client = TestClient(_app(user))
        response = client.post(
            "/api/v1/mail/send",
            json={"to": "steve@fastmail.com", "subject": "x", "body": "hi", "confirm": False},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Confirm", response.json()["detail"])

    def test_redact_fastmail_token(self):
        self.assertNotIn("fmu1-abcd1234secret", redact_secrets("token=fmu1-abcd1234secret"))

    def test_mail_module_has_no_owner_email_string(self):
        import inspect
        import app.services.mail as mail_mod

        source = inspect.getsource(mail_mod)
        self.assertNotIn("stevebitsko", source)
        self.assertNotIn("owner account", source)


class MailToolTests(unittest.TestCase):
    def test_summarize_unread_matches(self):
        self.assertTrue(mail_tool.wants_unread_mail("summarize unread"))
        self.assertTrue(mail_tool.wants_unread_mail("unread mail please"))
        self.assertFalse(mail_tool.wants_unread_mail("hello"))

    def test_markdown_list(self):
        text = mail_tool.unread_mail_markdown(
            [{"from": "Ada", "subject": "Hi", "date": "2026-09-15", "unseen": True}]
        )
        self.assertIn("Ada", text)
        self.assertIn("cap 50", text)


if __name__ == "__main__":
    unittest.main()
