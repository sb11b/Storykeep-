from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi import HTTPException

from app.services.chat import build_xai_messages, enforce_rate_limit, thread_window, validate_payload, _rate_hits


class ChatGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        _rate_hits.clear()

    def test_rejects_empty_and_huge(self):
        with self.assertRaises(HTTPException):
            validate_payload([])
        with self.assertRaises(HTTPException):
            validate_payload([{"role": "assistant", "content": "hi"}])
        with self.assertRaises(HTTPException):
            validate_payload([{"role": "user", "content": "x" * 40_000}])
        cleaned = validate_payload([{"role": "user", "content": "What is this about?"}])
        self.assertEqual(cleaned[0]["role"], "user")
        twelve_k = validate_payload([{"role": "user", "content": "x" * 12_000}])
        self.assertEqual(len(twelve_k[0]["content"]), 12_000)

    def test_chat_in_accepts_a_large_paste_instead_of_422(self):
        from pydantic import ValidationError
        from app.routers.chat import ChatIn

        body = ChatIn(message="x" * 24_000)
        self.assertEqual(len(body.message), 24_000)
        with self.assertRaises(ValidationError):
            ChatIn(message="x" * 100_001)

    def test_excerpt_is_capped(self):
        from types import SimpleNamespace
        from app.services.chat import article_excerpt

        article = SimpleNamespace(title="Long", content_text="word " * 8000, content_html=None, summary=None)
        excerpt = article_excerpt(article)
        from app.services.include_chunk import INCLUDE_TURN_CHAR_MAX

        self.assertLessEqual(len(excerpt), INCLUDE_TURN_CHAR_MAX + 240)
        self.assertIn("Title: Long", excerpt)
        self.assertIn("§", excerpt)

    def test_general_mode_prompt_allows_outside_knowledge(self):
        messages = build_xai_messages([{"role": "user", "content": "Explain GDP"}], None, include_article=False)
        system = messages[0]["content"]
        self.assertIn("general-knowledge mode", system)
        self.assertIn("Do not refuse questions because no article is attached", system)
        self.assertNotIn("Current article excerpt", system)

    def test_system_prompt_steers_school_coding_and_fenced_code(self):
        messages = build_xai_messages([{"role": "user", "content": "python average"}], None, include_article=False)
        system = messages[0]["content"].lower()
        self.assertIn("school coding", system)
        self.assertIn("fenced markdown", system)
        self.assertIn("```python", messages[0]["content"])
        self.assertNotIn("cannot generate images", system)
        self.assertNotIn("faceapp", system)
        self.assertIn("imagine", system)
        self.assertNotIn("already applied", system)
        self.assertNotIn("imagine will apply", system)

    def test_system_prompt_does_not_claim_no_image_tools(self):
        from app.services.chat import SYSTEM_PROMPT

        lower = SYSTEM_PROMPT.lower()
        self.assertNotIn("doesn't have image tools", lower)
        self.assertNotIn("does not have image tools", lower)
        self.assertNotIn("cannot generate images", lower)
        self.assertNotIn("faceapp", lower)
        self.assertIn("imagine", lower)
        self.assertNotIn("already applied", lower)
        self.assertNotIn("imagine will apply", lower)
        self.assertNotIn("use the imagine", lower)
        self.assertNotIn("if this reply has no", lower)
        self.assertNotIn("do not treat the word", lower)
        self.assertNotIn("denylist", lower)
        self.assertNotIn("according to the system", lower)
        self.assertNotIn("system instructions", lower)
        self.assertIn("add to notes", lower)
        self.assertIn("word next to copy", lower)
        self.assertNotIn("if steve wants a reply kept, tell him to use add to notes", lower)
        self.assertIn("never append a keep/notes footer", lower)
        self.assertIn("photo metadata", lower)
        self.assertIn("never ask him to attach a photo", lower)
        self.assertNotIn("please attach", lower)

    def test_owner_upload_prompt_transcribes_without_copyright_lecture(self):
        from app.services.chat import ATTACHMENT_MODE_APPEND

        lower = ATTACHMENT_MODE_APPEND.lower()
        self.assertIn("transcribe", lower)
        self.assertIn("do not give a copyright lecture", lower)
        self.assertIn("owner-uploaded", lower)

    def test_article_mode_includes_excerpt(self):
        excerpt = "Title: Demo\n\nBody text"
        messages = build_xai_messages([{"role": "user", "content": "Summarize"}], excerpt, include_article=True)
        system = messages[0]["content"]
        self.assertIn("Current article excerpt", system)
        self.assertIn("Body text", system)
        self.assertIn("Answer from this article excerpt only", system)
        self.assertIn("Do not use other StoryKeep notes or the rest of the vault", system)

    def test_note_include_is_capped_and_not_the_vault(self):
        note = "Title: Lab\n\nOnly this note"
        messages = build_xai_messages(
            [{"role": "user", "content": "Summarize"}],
            None,
            include_article=False,
            include_note=True,
            note_excerpt=note,
        )
        system = messages[0]["content"]
        self.assertIn("Included note excerpt", system)
        self.assertIn("Only this note", system)
        self.assertIn("not the whole vault", system)
        self.assertNotIn("Current article excerpt", system)
        self.assertNotIn("general-knowledge mode", system)

    def test_thread_window_limits_context(self):
        history = [{"role": "user", "content": f"line {index}"} for index in range(20)]
        windowed = thread_window(history, limit=6)
        self.assertEqual(len(windowed), 6)
        self.assertEqual(windowed[-1]["content"], "line 19")

    def test_thread_window_default_is_twelve(self):
        history = [{"role": "user", "content": f"line {index}"} for index in range(20)]
        windowed = thread_window(history)
        self.assertEqual(len(windowed), 12)
        self.assertEqual(windowed[0]["content"], "line 8")

    def test_oversized_include_is_rejected_before_xai(self):
        from app.services.chat import SEND_CONTEXT_TOO_LARGE, reject_oversized_send

        with self.assertRaises(HTTPException) as caught:
            reject_oversized_send(
                [{"role": "user", "content": "summarize this"}],
                article_body="x" * 24_001,
            )
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(caught.exception.detail, SEND_CONTEXT_TOO_LARGE)
        reject_oversized_send([{"role": "user", "content": "hello"}], article_body="short")
        reject_oversized_send(
            [{"role": "user", "content": "summarize this heading"}],
            article_body="x" * 10_000,
        )

    def test_drop_trailing_assistants_ends_on_user(self):
        from app.services.chat import drop_trailing_assistants

        history = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "partial"},
        ]
        cleaned = drop_trailing_assistants(history)
        self.assertEqual(cleaned[-1]["role"], "user")
        self.assertEqual(cleaned[-1]["content"], "hello")

    def test_messages_for_xai_drops_partial_assistant(self):
        from app.services.chat import messages_for_xai

        prepared = messages_for_xai(
            [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "partial"},
            ],
            model="grok-4",
        )
        self.assertEqual(prepared[-1]["role"], "user")
        self.assertEqual(prepared[-1]["content"], "hello")

    def test_rate_limit_caps_hourly_requests(self):
        from app.config import settings

        user = uuid4()
        now = 1_700_000_000.0
        limit = int(settings.chat_requests_per_hour or 120)
        for index in range(limit):
            enforce_rate_limit(user, now=now + index)
        with self.assertRaises(HTTPException) as caught:
            enforce_rate_limit(user, now=now + limit + 1)
        self.assertEqual(caught.exception.status_code, 429)
        enforce_rate_limit(user, now=now + 3601)

    def test_hello_payload_has_no_code_interpreter(self):
        from app.services.chat import build_chat_completions_payload, map_xai_http_error

        payload = build_chat_completions_payload(
            messages=[{"role": "user", "content": "hello"}],
            model="grok-4.6",
            reasoning_effort="low",
            max_tokens=256,
            stream=True,
            temperature=0.6,
        )
        self.assertNotIn("tools", payload)
        self.assertEqual(payload["messages"][-1]["content"], "hello")
        mapped = map_xai_http_error(422, "unknown variant `code_interpreter`", "grok-4.6")
        self.assertEqual(mapped.status_code, 502)
        self.assertEqual(mapped.detail, "unknown variant `code_interpreter`")
        self.assertNotIn("xAI HTTP 422", str(mapped.detail))


if __name__ == "__main__":
    unittest.main()
