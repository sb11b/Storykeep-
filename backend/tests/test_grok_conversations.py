from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock
from uuid import uuid4

from fastapi import HTTPException

from app.services.chat import (
    MODEL_AUTO,
    CHAT_FIRST_BYTE_TIMEOUT_SEC,
    XAI_SILENT_DETAIL,
    ARTICLE_CHAR_CAP,
    XAI_CONTEXT_MESSAGES,
    build_xai_messages,
    chat_error_message,
    default_fast_model,
    default_full_model,
    key_format_ok,
    parse_xai_error_body,
    pick_fast_for_auto,
    resolve_model_for_request,
    resolve_reasoning_for_request,
    stream_error_event,
    thread_window,
    validate_payload,
    _parse_sse_chunk,
)
from app.services.grok_conversations import resolve_patched_title, should_persist, title_from_user_line


class GrokConversationTests(unittest.TestCase):
    def test_title_from_first_user_line_truncates(self):
        self.assertEqual(title_from_user_line("Explain Python lists"), "Explain Python lists")
        long_line = "x" * 100
        title = title_from_user_line(long_line)
        self.assertLessEqual(len(title), 80)
        self.assertTrue(title.endswith("…"))

    def test_demo_accounts_do_not_persist(self):
        demo = SimpleNamespace(email="steve@storykeep.local", is_demo_locked=True)
        live = SimpleNamespace(email="reader@example.com", is_demo_locked=False)
        self.assertFalse(should_persist(demo))
        self.assertTrue(should_persist(live))

    def test_thread_window_keeps_latest_messages(self):
        history = [{"role": "user" if index % 2 == 0 else "assistant", "content": f"m{index}"} for index in range(20)]
        windowed = thread_window(history, limit=4)
        self.assertEqual(len(windowed), 4)
        self.assertEqual(windowed[-1]["content"], "m19")

    def test_build_xai_messages_uses_window_not_full_history(self):
        history = [{"role": "user" if index % 2 == 0 else "assistant", "content": f"m{index}"} for index in range(20)]
        messages = build_xai_messages(history, None, include_article=False)
        body = [item for item in messages if item["role"] != "system"]
        self.assertEqual(len(body), 12)
        self.assertEqual(body[-1]["content"], "m19")

    def test_build_xai_messages_recap_toggle(self):
        history = [{"role": "user", "content": "What is GDP?"}]
        direct = build_xai_messages(history, None, include_article=False, recap_question=False)
        recap = build_xai_messages(history, None, include_article=False, recap_question=True)
        self.assertIn("Answer directly", direct[0]["content"])
        self.assertIn("Recap my question", recap[0]["content"])
        self.assertNotIn("Recap my question", direct[0]["content"])

    def test_empty_patch_title_falls_back_to_first_user_message(self):
        self.assertEqual(resolve_patched_title("", "Explain Python lists"), "Explain Python lists")
        self.assertEqual(resolve_patched_title("   ", "First question"), "First question")
        self.assertEqual(resolve_patched_title("", None), "New chat")

    def test_non_empty_patch_title_is_used(self):
        self.assertEqual(resolve_patched_title("My homework", "ignored"), "My homework")

    def test_patch_conversation_stores_saved_note_id(self) -> None:
        from unittest.mock import MagicMock

        from app.services.grok_conversations import patch_conversation_for_user

        user_id = uuid4()
        conversation_id = uuid4()
        note_id = uuid4()
        row = SimpleNamespace(id=conversation_id, user_id=user_id, saved_note_id=None, title="New chat")
        db = MagicMock()
        db.scalar.return_value = row
        patched = patch_conversation_for_user(
            db,
            user_id,
            conversation_id,
            saved_note_id=note_id,
            saved_note_provided=True,
        )
        self.assertEqual(patched.saved_note_id, note_id)
        db.add.assert_called()

    def test_auto_keeps_normal_turns_on_low(self):
        from app.services.chat import CURRENT_CHAT_MODEL, AUTO_LOW_MAX_CHARS

        self.assertTrue(pick_fast_for_auto("hello"))
        self.assertEqual(resolve_model_for_request(MODEL_AUTO, "hello", []), CURRENT_CHAT_MODEL)
        self.assertEqual(resolve_reasoning_for_request(MODEL_AUTO, "auto", "hello", []), "low")
        self.assertEqual(
            resolve_reasoning_for_request(MODEL_AUTO, "auto", "how was your morning", []),
            "low",
        )
        long_history = [{"role": "assistant", "content": "Here is a python function and a plan.\n" + ("x" * 500)}]
        self.assertEqual(
            resolve_reasoning_for_request(MODEL_AUTO, "auto", "how was your morning", long_history),
            "low",
        )
        prompt = "Debug this Python function:\n```python\ndef avg(nums):\n    return sum(nums)/len(nums)\n```\n" + ("x" * 400)
        self.assertFalse(pick_fast_for_auto(prompt))
        self.assertEqual(resolve_model_for_request(MODEL_AUTO, prompt, []), CURRENT_CHAT_MODEL)
        self.assertEqual(resolve_reasoning_for_request(MODEL_AUTO, "auto", prompt, []), "xhigh")
        dat_plan = "DAT plan\n" + ("Week 1 analyze the dataset and rewrite paper notes.\n" * 20)
        self.assertGreaterEqual(len(dat_plan), AUTO_LOW_MAX_CHARS)
        self.assertEqual(resolve_reasoning_for_request(MODEL_AUTO, "auto", dat_plan, []), "xhigh")
        self.assertEqual(resolve_reasoning_for_request(MODEL_AUTO, "auto", "please analyze this", []), "low")
        self.assertEqual(resolve_reasoning_for_request(MODEL_AUTO, "auto", "what is photo metadata", []), "low")
        self.assertEqual(
            resolve_reasoning_for_request(MODEL_AUTO, "auto", "write a prompt for cursor to fix the login bug", []),
            "xhigh",
        )
        ramble = "Hey, just checking in. " * 40
        self.assertGreaterEqual(len(ramble), AUTO_LOW_MAX_CHARS)
        self.assertEqual(resolve_reasoning_for_request(MODEL_AUTO, "auto", ramble, []), "low")

    def test_auto_uses_xhigh_for_school_code_and_long_analyze(self):
        self.assertEqual(
            resolve_reasoning_for_request(MODEL_AUTO, "auto", "think harder about this proof", []),
            "low",
        )
        self.assertEqual(
            resolve_reasoning_for_request(MODEL_AUTO, "auto", "do a deep dive on my schema", []),
            "low",
        )
        self.assertTrue(pick_fast_for_auto("think harder about this proof"))
        self.assertEqual(
            resolve_reasoning_for_request(MODEL_AUTO, "auto", "help with this python homework", []),
            "low",
        )
        long_homework = "help with this python homework\n" + ("notes " * 80)
        self.assertGreaterEqual(len(long_homework), 400)
        self.assertEqual(resolve_reasoning_for_request(MODEL_AUTO, "auto", long_homework, []), "xhigh")
        long_analyze = "Please analyze this dataset. " + ("notes " * 80)
        self.assertGreaterEqual(len(long_analyze), 400)
        self.assertEqual(resolve_reasoning_for_request(MODEL_AUTO, "auto", long_analyze, []), "xhigh")

    def test_locked_model_skips_auto_routing(self):
        resolved = resolve_model_for_request("grok-4.6", "hi", [])
        self.assertEqual(resolved, "grok-4.6")
        self.assertEqual(resolve_model_for_request("grok-4", "hi", []), "grok-4.6")
        self.assertEqual(resolve_reasoning_for_request("grok-4.6", "high", "hello", []), "high")
        self.assertEqual(resolve_reasoning_for_request("grok-4.6", "xhigh", "hello", []), "low")
        self.assertEqual(resolve_reasoning_for_request("grok-4.6", "xhigh", "help with this python homework", []), "low")
        long_homework = "help with this python homework\n" + ("notes " * 80)
        self.assertEqual(resolve_reasoning_for_request("grok-4.6", "xhigh", long_homework, []), "xhigh")

    def test_rewrites_dead_fast_alias(self):
        from app.services.chat import CURRENT_CHAT_MODEL, CURRENT_FAST_MODEL, rewrite_xai_model

        self.assertEqual(rewrite_xai_model("grok-4-fast-non-reasoning"), CURRENT_FAST_MODEL)
        self.assertEqual(rewrite_xai_model("grok-4-fast"), CURRENT_FAST_MODEL)
        self.assertEqual(rewrite_xai_model("grok-4"), CURRENT_CHAT_MODEL)
        self.assertEqual(rewrite_xai_model("grok-4.6"), CURRENT_CHAT_MODEL)
        self.assertEqual(rewrite_xai_model("grok-4.20-0309-non-reasoning"), CURRENT_FAST_MODEL)

    def test_long_reply_output_and_idle_budget(self):
        from app.services.chat import (
            CHAT_FIRST_BYTE_TIMEOUT_SEC,
            JUNIOR_MAX_RESPONSE_WORDS,
            MAX_TOKENS_CAP,
            chat_idle_after_token_sec,
            chat_idle_timeout_detail,
            posted_spend_label,
            resolved_max_output_tokens,
        )

        self.assertEqual(CHAT_FIRST_BYTE_TIMEOUT_SEC, 45.0)
        self.assertEqual(JUNIOR_MAX_RESPONSE_WORDS, 100_000)
        self.assertEqual(MAX_TOKENS_CAP, 125_000)
        self.assertEqual(resolved_max_output_tokens(), 125_000)
        with mock.patch("app.services.chat.settings") as mocked:
            mocked.xai_chat_max_tokens = 2048
            self.assertEqual(resolved_max_output_tokens(), 125_000)
        self.assertGreaterEqual(chat_idle_after_token_sec(), 120.0)
        self.assertIn("waiting for the next token", chat_idle_timeout_detail())
        self.assertEqual(posted_spend_label("grok-4.6", "low"), "4.6 · low")

    def test_chat_error_message_includes_http_status(self):
        message = chat_error_message(504, "Grok timed out after 90s.")
        self.assertIn("HTTP 504", message)
        self.assertIn("timed out", message)

    def test_parse_xai_error_body_reads_json_message(self):
        body = '{"error":{"message":"rate limit exceeded","code":"429"}}'
        self.assertEqual(parse_xai_error_body(body, 429), "rate limit exceeded")

    def test_stream_error_event_marks_partial(self):
        event = stream_error_event(504, "Grok timed out.", partial=True)
        self.assertTrue(event["partial"])
        self.assertIn("HTTP 504", event["error"])

    def test_validate_payload_accepts_windowed_history(self):
        history = [{"role": "user", "content": f"m{index}"} for index in range(30)]
        windowed = thread_window(history)
        cleaned = validate_payload(windowed)
        self.assertEqual(cleaned[-1]["role"], "user")

    def test_parse_sse_chunk_reasoning_is_activity_not_visible(self):
        raw = '{"choices":[{"delta":{"reasoning_content":"thinking"}}]}'
        text, active = _parse_sse_chunk(raw)
        self.assertEqual(text, "")
        self.assertTrue(active)

    def test_parse_sse_chunk_returns_visible_content(self):
        raw = '{"choices":[{"delta":{"content":"Hello"}}]}'
        text, active = _parse_sse_chunk(raw)
        self.assertEqual(text, "Hello")
        self.assertTrue(active)

    def test_parse_sse_chunk_reads_array_content(self):
        raw = '{"choices":[{"delta":{"content":[{"type":"text","text":"Hel"},{"type":"text","text":"lo"}]}}]}'
        text, active = _parse_sse_chunk(raw)
        self.assertEqual(text, "Hello")
        self.assertTrue(active)

    def test_parse_sse_chunk_reads_delta_text_field(self):
        raw = '{"choices":[{"delta":{"text":"Hi"}}]}'
        text, active = _parse_sse_chunk(raw)
        self.assertEqual(text, "Hi")
        self.assertTrue(active)

    def test_default_chat_model_is_grok_46(self):
        self.assertEqual(default_full_model(), "grok-4.6")
        self.assertTrue(default_fast_model())

    def test_key_format_ok_requires_xai_prefix(self):
        self.assertIsInstance(key_format_ok(), bool)

    def test_stream_error_event_includes_message(self):
        event = stream_error_event(504, "Grok timed out after 45s.")
        self.assertEqual(event["message"], "Grok timed out after 45s.")

    def test_first_byte_timeout_is_eight_seconds_xai_silent(self):
        self.assertEqual(CHAT_FIRST_BYTE_TIMEOUT_SEC, 45.0)
        self.assertEqual(XAI_SILENT_DETAIL, "xAI silent")
        event = stream_error_event(504, XAI_SILENT_DETAIL)
        self.assertEqual(event["message"], "xAI silent")
        self.assertIn("xAI silent", event["error"])

    def test_encode_sse_is_a_flushable_chunk(self):
        from app.services.chat import SSE_PADDING, encode_sse

        chunk = encode_sse({"delta": "Hi"})
        self.assertTrue(chunk.endswith(b"\n\n"))
        self.assertIsInstance(chunk, bytes)
        self.assertGreater(len(SSE_PADDING), 4000)
        self.assertTrue(SSE_PADDING.startswith(b":"))

    def test_context_caps(self):
        self.assertEqual(XAI_CONTEXT_MESSAGES, 12)
        self.assertEqual(ARTICLE_CHAR_CAP, 10_000)


if __name__ == "__main__":
    unittest.main()
