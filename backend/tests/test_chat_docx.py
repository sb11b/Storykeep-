from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.database import get_db
from app.deps import get_current_user
from app.routers import chat as chat_router
from app.services.chat_docx import (
    DOCX_MEDIA_TYPE,
    EMPTY_WORD_BODY,
    build_message_docx,
    document_xml,
    docx_filename,
    docx_title,
    has_word_body,
)
from app.services.demo_lock import reject_locked
from app.services.grok_conversations import owned_assistant_message


DAT_PAPER = """# Grammar-fixed DAT-200 paper

This paper explains how a relational schema stores student grades without dropping rows.

## References

Smith, J. (2020). Databases for students. Journal of Learning, 4(2), 10-20.

Lee, A. (2019). Query plans. Publisher.
"""


class ChatDocxTests(unittest.TestCase):
    def test_title_from_first_heading(self):
        self.assertEqual(docx_title(DAT_PAPER), "Grammar-fixed DAT-200 paper")
        self.assertEqual(docx_filename(DAT_PAPER), "Grammar-fixed DAT-200 paper.docx")
        self.assertEqual(docx_filename("Just a line\n\nMore."), "Just a line.docx")
        self.assertEqual(docx_title("Just a line\n\nMore."), "Just a line")
        self.assertEqual(docx_filename('DAT-200: "quotes"/win*.md'), "DAT-200- -quotes--win-.md.docx")

    def test_hides_empty_and_tool_only(self):
        self.assertFalse(has_word_body("   "))
        self.assertFalse(has_word_body("![](/api/v1/media/abc)\n"))
        self.assertFalse(has_word_body("```json\n{\"tool\":\"code_interpreter\"}\n```"))
        self.assertFalse(has_word_body('{"tool":"code_interpreter","ok":true}'))
        self.assertTrue(has_word_body(DAT_PAPER))

    def test_docx_is_tnr_with_hanging_references(self):
        payload = build_message_docx(DAT_PAPER)
        self.assertTrue(payload.startswith(b"PK"))
        xml = document_xml(payload)
        self.assertIn("Times New Roman", xml)
        self.assertIn("Grammar-fixed DAT-200 paper", xml)
        self.assertIn("relational schema", xml)
        self.assertIn("Smith, J.", xml)
        self.assertIn('w:hanging="720"', xml)
        self.assertIn("1440", xml)
        from io import BytesIO

        from docx import Document

        opened = Document(BytesIO(payload))
        texts = [para.text for para in opened.paragraphs]
        self.assertTrue(any("Grammar-fixed DAT-200 paper" in text for text in texts))
        self.assertTrue(any("relational schema" in text for text in texts))
        self.assertTrue(any("Smith, J." in text for text in texts))

    def test_empty_reply_raises(self):
        with self.assertRaises(ValueError) as raised:
            build_message_docx("   ")
        self.assertEqual(str(raised.exception), EMPTY_WORD_BODY)

    def test_owned_assistant_message_404_for_user_or_wrong_role(self):
        db = MagicMock()
        db.scalar.return_value = None
        user = SimpleNamespace(id=uuid.uuid4(), email="reader@example.com", is_demo_locked=False)
        with self.assertRaises(HTTPException) as missing:
            owned_assistant_message(db, user, uuid.uuid4())
        self.assertEqual(missing.exception.status_code, 404)
        db.scalar.return_value = SimpleNamespace(role="user", content="hi")
        with self.assertRaises(HTTPException) as user_turn:
            owned_assistant_message(db, user, uuid.uuid4())
        self.assertEqual(user_turn.exception.status_code, 404)

    def test_demo_locked_is_off(self):
        with self.assertRaises(HTTPException) as caught:
            reject_locked(SimpleNamespace(email="steve@storykeep.local", is_demo_locked=True))
        self.assertEqual(caught.exception.status_code, 403)

    def test_unauth_docx_is_401_json(self):
        app = FastAPI()
        app.include_router(chat_router.router, prefix="/api/v1")

        def fake_db():
            yield MagicMock()

        app.dependency_overrides[get_db] = fake_db
        client = TestClient(app)
        response = client.post(f"/api/v1/chat/messages/{uuid.uuid4()}/docx")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Not authenticated"})

    def test_owner_download_returns_docx_attachment(self):
        message_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4(), email="reader@example.com", is_demo_locked=False)
        row = SimpleNamespace(id=message_id, role="assistant", content=DAT_PAPER)
        db = MagicMock()

        def fake_db():
            yield db

        def fake_user():
            return user

        app = FastAPI()
        app.include_router(chat_router.router, prefix="/api/v1")
        app.dependency_overrides[get_db] = fake_db
        app.dependency_overrides[get_current_user] = fake_user
        from unittest.mock import patch

        with patch("app.services.grok_conversations.owned_assistant_message", return_value=row), patch(
            "app.services.grok_conversations.should_persist", return_value=True
        ):
            client = TestClient(app)
            response = client.post(f"/api/v1/chat/messages/{message_id}/docx")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"].split(";")[0], DOCX_MEDIA_TYPE)
        self.assertIn("attachment", response.headers.get("content-disposition", ""))
        self.assertIn(".docx", response.headers.get("content-disposition", ""))
        self.assertIn("Grammar-fixed DAT-200 paper.docx", response.headers.get("content-disposition", ""))
        self.assertTrue(response.content.startswith(b"PK"))
        xml = document_xml(response.content)
        self.assertIn("Grammar-fixed DAT-200 paper", xml)
        self.assertIn("Smith, J.", xml)

    def test_empty_reply_docx_is_400(self):
        message_id = uuid.uuid4()
        user = SimpleNamespace(id=uuid.uuid4(), email="reader@example.com", is_demo_locked=False)
        row = SimpleNamespace(id=message_id, role="assistant", content="   ")
        db = MagicMock()

        def fake_db():
            yield db

        app = FastAPI()
        app.include_router(chat_router.router, prefix="/api/v1")
        app.dependency_overrides[get_db] = fake_db
        app.dependency_overrides[get_current_user] = lambda: user
        from unittest.mock import patch

        with patch("app.services.grok_conversations.owned_assistant_message", return_value=row), patch(
            "app.services.grok_conversations.should_persist", return_value=True
        ):
            client = TestClient(app)
            response = client.post(f"/api/v1/chat/messages/{message_id}/docx")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": EMPTY_WORD_BODY})

    def test_clean_copy_strips_grammar_marks(self):
        from app.services.school_tools import strip_marks

        marked = "This is a well-==known== method.\n\n## References\n\nSmith, J. (2020). Databases."
        clean = strip_marks(marked)
        self.assertNotIn("==", clean)
        payload = build_message_docx(clean)
        xml = document_xml(payload)
        self.assertIn("well-known", xml)
        self.assertNotIn("==", xml)


if __name__ == "__main__":
    unittest.main()
