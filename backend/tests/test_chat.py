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
        clipped = validate_payload([{"role": "user", "content": "x" * 40_000}])
        from app.services.chat import MERGED_MESSAGE_CHAR_CAP

        self.assertLessEqual(len(clipped[0]["content"]), MERGED_MESSAGE_CHAR_CAP)
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

    def test_build_xai_messages_does_not_double_core_prompt(self):
        from app.services.chat import SYSTEM_PROMPT

        extra = "Owner note: keep answers short."
        messages = build_xai_messages(
            [{"role": "user", "content": "hi"}],
            None,
            include_article=False,
            extra_system=extra,
        )
        system = messages[0]["content"]
        self.assertEqual(system.count("school coding assistant"), 1)
        self.assertIn(extra, system)
        doubled = build_xai_messages(
            [{"role": "user", "content": "hi"}],
            None,
            include_article=False,
            extra_system=SYSTEM_PROMPT + "\n\n" + extra,
        )
        self.assertEqual(doubled[0]["content"].count("school coding assistant"), 1)

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
        self.assertIn("web_search", lower)
        self.assertNotIn("browse the live web", lower)
        self.assertNotIn("cannot execute tools", lower)
        self.assertIn("must call web_search", lower)
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
                article_body="x" * 120_001,
            )
        self.assertEqual(caught.exception.status_code, 413)
        self.assertEqual(caught.exception.detail, SEND_CONTEXT_TOO_LARGE)
        reject_oversized_send([{"role": "user", "content": "hello"}], article_body="short")
        reject_oversized_send(
            [{"role": "user", "content": "summarize this heading"}],
            article_body="x" * 10_000,
        )

    def test_reject_oversized_send_uses_recent_thread_only(self):
        from app.services.chat import reject_oversized_send

        long_thread = [
            {"role": "user" if index % 2 == 0 else "assistant", "content": "x" * 5_000}
            for index in range(40)
        ]
        reject_oversized_send(long_thread)
        with self.assertRaises(HTTPException) as caught:
            reject_oversized_send(
                [{"role": "user", "content": "x" * 150_000}],
                working_excerpt="y" * 60_000,
            )
        self.assertEqual(caught.exception.status_code, 413)
        self.assertIn("too long", caught.exception.detail.lower())

    def test_long_thread_with_attachment_survives_validate(self):
        from app.services.chat import MERGED_MESSAGE_CHAR_CAP, messages_for_xai, messages_char_count

        spec_extract = "Figure 8.5 network diagram " + ("detail " * 1500)
        history: list[dict] = []
        history.append(
            {
                "role": "user",
                "content": "Summarize this spec",
                "files": [
                    {
                        "filename": "PHASE1_SPEC.md",
                        "kind": "file",
                        "extract_text": spec_extract[:12_000],
                    }
                ],
            }
        )
        history.append({"role": "assistant", "content": "Overview of phase one architecture."})
        for index in range(2, 24):
            if index % 2 == 0:
                history.append({"role": "user", "content": f"What about section {index}? Figure 8.5?"})
            else:
                history.append({"role": "assistant", "content": f"Section {index} covers layers and routing." * 40})
        prepared = messages_for_xai(history, model="grok-4.6")
        cleaned = validate_payload(prepared)
        self.assertEqual(cleaned[-1]["role"], "user")
        self.assertIn("Figure 8.5", cleaned[-1]["content"])
        self.assertLessEqual(len(cleaned[-1]["content"]), MERGED_MESSAGE_CHAR_CAP)
        self.assertLessEqual(messages_char_count(cleaned), 120_000)

    def test_thread_trim_cap_shrinks_when_working_note_attached(self):
        from app.services.chat import _THREAD_TRIM_MIN, thread_trim_cap

        bare = thread_trim_cap()
        with_work = thread_trim_cap(system_overhead=80_000)
        self.assertLess(with_work, bare)
        self.assertGreaterEqual(with_work, _THREAD_TRIM_MIN)

    def test_cap_working_excerpt_keeps_thread_room(self):
        from app.services.chat import cap_working_excerpt

        huge = "w" * 80_000
        capped = cap_working_excerpt(huge, thread_chars=170_000)
        self.assertIsNotNone(capped)
        assert capped is not None
        self.assertLess(len(capped), len(huge))
        self.assertGreaterEqual(len(capped), 8_000)

    def test_first_byte_timeout_scales_with_attachments(self):
        from app.services.chat import first_byte_timeout_sec

        hello = first_byte_timeout_sec(message_chars=200)
        self.assertGreaterEqual(hello, 45.0)
        heavy = first_byte_timeout_sec(
            message_chars=70_000,
            has_attachments=True,
            has_working_note=True,
            reasoning_effort="xhigh",
        )
        self.assertLess(hello, heavy)
        self.assertGreaterEqual(heavy, 60.0)
        self.assertLessEqual(heavy, 90.0)

    def test_map_xai_context_length_maps_to_thread_error(self):
        from app.services.chat import SEND_THREAD_TOO_LARGE, map_xai_http_error

        mapped = map_xai_http_error(400, "context length exceeded", "grok-4.6")
        self.assertEqual(mapped.status_code, 413)
        self.assertEqual(mapped.detail, SEND_THREAD_TOO_LARGE)

    def test_trim_prepared_shortens_old_assistant_turns(self):
        from app.services.chat import _trim_prepared_for_cap, messages_char_count

        prepared = [
            {"role": "user", "content": "see spec"},
            {"role": "assistant", "content": "y" * 20_000},
            {"role": "user", "content": "figure 8.5?"},
        ]
        trimmed = _trim_prepared_for_cap(prepared, 12_000)
        self.assertLess(messages_char_count(trimmed), messages_char_count(prepared))
        self.assertLessEqual(len(trimmed[-1]["content"]), len(prepared[-1]["content"]) + 1)

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
        from app.services.chat import build_chat_completions_payload, map_xai_http_error, should_attach_chat_tools

        self.assertFalse(should_attach_chat_tools("hello"))
        payload = build_chat_completions_payload(
            messages=[{"role": "user", "content": "hello"}],
            model="grok-4.6",
            reasoning_effort="low",
            max_tokens=256,
            stream=True,
            temperature=0.6,
            tools=[{"type": "code_interpreter"}],
        )
        blob = str(payload)
        self.assertNotIn("code_interpreter", blob)
        self.assertNotIn("tools", payload)
        self.assertEqual(payload["messages"][-1]["content"], "hello")
        mapped = map_xai_http_error(422, "unknown variant `code_interpreter`", "grok-4.6")
        self.assertEqual(mapped.status_code, 502)
        self.assertEqual(mapped.detail, "unknown variant `code_interpreter`")
        self.assertNotIn("xAI HTTP 422", str(mapped.detail))


if __name__ == "__main__":
    unittest.main()
