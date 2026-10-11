"""Junior email + document-file tools: pure mapping, draft-only safety, routing.

No network: the JMAP service calls are patched, and the pure mappers are
exercised directly. The never-send invariant is asserted against the router
source itself.
"""

from __future__ import annotations

import ast
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.deps import get_current_user
from app.routers import junior_email, junior_shared
from app.services import fastmail_jmap as jmap
from app.services import file_extract
from app.services import junior_shared_files
from app.services import mail as mail_service

ROUTER_SOURCE = Path(junior_email.__file__).read_text(encoding="utf-8")
JMAP_SOURCE = Path(jmap.__file__).read_text(encoding="utf-8")


def _owner():
    return SimpleNamespace(id=uuid.uuid4(), email="steve@fastmail.com", is_demo_locked=False)


def _app():
    app = FastAPI()
    app.include_router(junior_shared.router, prefix="/api/v1")

    def fake_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_user] = lambda: _owner()
    return app


def _email_row(**over):
    row = {
        "id": "M1",
        "from": "Jennifer <jennifer@example.com>",
        "to": "thebitskogroup@fastmail.com",
        "subject": "Lunch Thursday",
        "date": "2026-10-10T12:00:00Z",
        "preview": "Are you free for lunch Thursday?",
        "unseen": True,
        "hasAttachment": False,
    }
    row.update(over)
    return row


class PureMappingTests(unittest.TestCase):
    def test_inbox_mapping_keeps_voice_friendly_fields(self):
        mapped = junior_email.map_inbox_items({"items": [_email_row()], "total": 1})
        self.assertEqual(len(mapped), 1)
        item = mapped[0]
        self.assertEqual(item.id, "M1")
        self.assertEqual(item.from_address, "Jennifer <jennifer@example.com>")
        self.assertEqual(item.subject, "Lunch Thursday")
        self.assertEqual(item.preview, "Are you free for lunch Thursday?")
        self.assertTrue(item.unread)

    def test_inbox_mapping_skips_rows_without_ids(self):
        mapped = junior_email.map_inbox_items({"items": [{"from": "x"}, _email_row(id="M2")]})
        self.assertEqual([m.id for m in mapped], ["M2"])

    def test_body_mapping_caps_at_8000_and_marks_excerpt(self):
        body = "x" * 10_000
        mapped = junior_email.map_email_body({"id": "M1", "subject": "s", "body": body})
        self.assertEqual(len(mapped.body), junior_email.BODY_EXCERPT_CHARS)
        self.assertTrue(mapped.excerpt)

    def test_body_mapping_short_body_not_marked(self):
        mapped = junior_email.map_email_body({"id": "M1", "subject": "s", "body": "short"})
        self.assertEqual(mapped.body, "short")
        self.assertFalse(mapped.excerpt)

    def test_file_text_mapping_caps_at_30000_and_marks_excerpt(self):
        mapped = junior_email.map_file_text("chapter.docx", "y" * 40_000)
        self.assertEqual(len(mapped.text), junior_email.FILE_TEXT_CAP)
        self.assertTrue(mapped.excerpt)

    def test_file_text_mapping_short_text_not_marked(self):
        mapped = junior_email.map_file_text("notes.txt", "chapter one")
        self.assertEqual(mapped.text, "chapter one")
        self.assertFalse(mapped.excerpt)

    def test_draft_mapping_marks_draft_true(self):
        mapped = junior_email.map_draft_created(
            {"id": "D1", "to": "a@b.com", "subject": "Hi", "from": "thebitskogroup@fastmail.com"}
        )
        self.assertTrue(mapped.draft)
        self.assertEqual(mapped.id, "D1")


class DraftSafetyTests(unittest.TestCase):
    """The never-send invariant: drafts are created, never submitted."""

    def test_router_source_never_calls_email_submission(self):
        # Scan the router's CODE identifiers (not comments/docstrings) for the
        # submission method — a draft is created, never submitted.
        tree = ast.parse(ROUTER_SOURCE)
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertNotIn("EmailSubmission", names)

    def test_create_draft_builds_a_drafts_mailbox_payload(self):
        create = jmap.build_draft_create(
            drafts_id="drafts-box",
            identity={"id": "ident-1", "email": "thebitskogroup@fastmail.com", "name": "Bitsko Group"},
            to_addr="a@b.com",
            subject="Hello",
            body="Body text",
            from_email="thebitskogroup@fastmail.com",
            reply_to="thebitskogroup@fastmail.com",
        )
        self.assertEqual(create["mailboxIds"], {"drafts-box": True})
        self.assertEqual(create["keywords"], {"$draft": True})
        self.assertEqual(create["to"], [{"email": "a@b.com"}])
        self.assertEqual(create["from"][0]["email"], "thebitskogroup@fastmail.com")
        self.assertEqual(create["replyTo"], [{"email": "thebitskogroup@fastmail.com"}])
        # No submission anywhere in the create payload.
        self.assertNotIn("EmailSubmission", str(create))

    def test_create_draft_threads_a_reply(self):
        create = jmap.build_draft_create(
            drafts_id="drafts-box",
            identity={"id": "ident-1", "email": "thebitskogroup@fastmail.com"},
            to_addr="a@b.com",
            subject="Re: Hello",
            body="Body",
            reply_target={
                "messageId": ["<orig@mail>"],
                "references": ["<older@mail>"],
                "threadId": "T1",
            },
        )
        self.assertEqual(create["inReplyTo"], "<orig@mail>")
        self.assertEqual(create["references"], ["<older@mail>", "<orig@mail>"])
        self.assertEqual(create["threadId"], "T1")

    def test_clean_draft_fields_rejects_bad_input_with_speakable_errors(self):
        with self.assertRaises(ValueError):
            jmap.clean_draft_fields("not-an-email", "s", "body")
        with self.assertRaises(ValueError):
            jmap.clean_draft_fields("a@b.com", "s", "   ")
        to_addr, subj, text = jmap.clean_draft_fields(" a@b.com ", "", " body ")
        self.assertEqual((to_addr, subj, text), ("a@b.com", "(no subject)", "body"))

    def test_draft_identity_prefers_business_env_id(self):
        identities = [
            {"id": "parent", "email": "bitsko@fastmail.com"},
            {"id": "business", "email": "thebitskogroup@fastmail.com"},
        ]
        with patch.object(jmap.settings, "fastmail_identity_business", "business"):
            self.assertEqual(
                jmap._draft_identity(identities),
                {"id": "business", "email": "thebitskogroup@fastmail.com"},
            )
        with patch.object(jmap.settings, "fastmail_identity_business", ""), patch.object(
            jmap.settings, "fastmail_from", "thebitskogroup@fastmail.com"
        ):
            self.assertEqual(
                jmap._draft_identity(identities),
                {"id": "business", "email": "thebitskogroup@fastmail.com"},
            )

    def test_send_path_is_not_reachable_from_this_router(self):
        # The router only imports create_draft — send_email (the EmailSubmission
        # path) is never referenced by the junior email surface.
        self.assertNotIn("send_email", ROUTER_SOURCE)


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(_app())
        patcher = patch.object(mail_service, "env_token", return_value="token-abc")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_inbox_route_maps_the_service_payload(self):
        with patch.object(
            jmap, "list_emails", return_value={"items": [_email_row()], "total": 1}
        ) as listed:
            response = self.client.get("/api/v1/junior/email/inbox?limit=5&unread_only=true")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body[0]["subject"], "Lunch Thursday")
        self.assertTrue(body[0]["unread"])
        listed.assert_called_once()
        self.assertEqual(listed.call_args.kwargs["limit"], 5)
        self.assertTrue(listed.call_args.kwargs["unseen"])

    def test_search_route_passes_the_query(self):
        with patch.object(
            jmap, "search_emails", return_value={"items": [_email_row(subject="Invoice")], "total": 1}
        ) as searched:
            response = self.client.get("/api/v1/junior/email/search?q=invoice")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["subject"], "Invoice")
        self.assertEqual(searched.call_args.kwargs["query"], "invoice")

    def test_message_route_returns_full_capped_body(self):
        with patch.object(
            jmap,
            "get_email",
            return_value={"id": "M1", "subject": "Long", "body": "z" * 9_000},
        ):
            response = self.client.get("/api/v1/junior/email/message/M1")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["body"]), junior_email.BODY_EXCERPT_CHARS)
        self.assertTrue(payload["excerpt"])

    def test_drafts_route_queries_the_drafts_role(self):
        with patch.object(jmap, "list_emails", return_value={"items": [], "total": 0}) as listed:
            response = self.client.get("/api/v1/junior/email/drafts")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(listed.call_args.kwargs["role"], "drafts")

    def test_draft_route_creates_a_draft_only(self):
        with patch.object(
            jmap,
            "create_draft",
            return_value={
                "id": "D1",
                "to": "a@b.com",
                "subject": "Hi",
                "from": "thebitskogroup@fastmail.com",
                "draft": True,
            },
        ) as created:
            response = self.client.post(
                "/api/v1/junior/email/draft",
                json={"to": "a@b.com", "subject": "Hi", "body": "Hello there"},
            )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["draft"])
        self.assertEqual(payload["id"], "D1")
        created.assert_called_once()

    def test_missing_token_is_a_clean_503(self):
        with patch.object(mail_service, "env_token", return_value=""), patch.object(
            mail_service, "stored_mail_token", return_value=""
        ), patch.object(mail_service, "stored_app_password", return_value=""):
            response = self.client.get("/api/v1/junior/email/inbox")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], junior_email.EMAIL_UNAVAILABLE)

    def test_file_text_route_extracts_plain_text(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.txt"
            path.write_text("chapter one body", encoding="utf-8")
            row = SimpleNamespace(
                id=uuid.uuid4(),
                document_slug="quantum",
                filename="notes.txt",
                storage_path=str(path),
            )
            with patch.object(junior_shared_files, "get_file", return_value=row):
                response = self.client.get(
                    f"/api/v1/junior/documents/quantum/files/{row.id}/text"
                )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["text"], "chapter one body")
        self.assertFalse(payload["excerpt"])
        self.assertEqual(payload["slug"], "quantum")

    def test_file_text_route_uses_the_docx_extractor_with_a_fake(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "chapter.docx"
            path.write_bytes(b"PK\x03\x04fake")
            row = SimpleNamespace(
                id=uuid.uuid4(),
                document_slug="school",
                filename="chapter.docx",
                storage_path=str(path),
            )
            with patch.object(junior_shared_files, "get_file", return_value=row), patch.object(
                file_extract, "_docx", lambda payload: "extracted docx body"
            ):
                response = self.client.get(f"/api/v1/junior/documents/school/files/{row.id}/text")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "extracted docx body")

    def test_file_text_route_unsupported_type_is_speakable_415(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "malware.exe"
            path.write_bytes(b"MZ")
            row = SimpleNamespace(
                id=uuid.uuid4(),
                document_slug="school",
                filename="malware.exe",
                storage_path=str(path),
            )
            with patch.object(junior_shared_files, "get_file", return_value=row):
                response = self.client.get(f"/api/v1/junior/documents/school/files/{row.id}/text")
        self.assertEqual(response.status_code, 415)
        self.assertIn("Cannot extract", response.json()["detail"])

    def test_file_text_route_slug_mismatch_is_404(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.txt"
            path.write_text("x", encoding="utf-8")
            row = SimpleNamespace(
                id=uuid.uuid4(),
                document_slug="quantum",
                filename="notes.txt",
                storage_path=str(path),
            )
            with patch.object(junior_shared_files, "get_file", return_value=row):
                response = self.client.get(f"/api/v1/junior/documents/other/files/{row.id}/text")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
