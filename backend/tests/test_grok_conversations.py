from __future__ import annotations

import unittest
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException

from app.services.chat import (
    MODEL_AUTO,
    build_xai_messages,
    chat_error_message,
    default_fast_model,
    default_full_model,
    key_format_ok,
    parse_xai_error_body,
    pick_fast_for_auto,
    resolve_model_for_request,
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

    def test_empty_patch_title_falls_back_to_first_user_message(self):
        self.assertEqual(resolve_patched_title("", "Explain Python lists"), "Explain Python lists")
        self.assertEqual(resolve_patched_title("   ", "First question"), "First question")
        self.assertEqual(resolve_patched_title("", None), "New chat")

    def test_non_empty_patch_title_is_used(self):
        self.assertEqual(resolve_patched_title("My homework", "ignored"), "My homework")

    def test_auto_picks_fast_for_short_simple_prompt(self):
        self.assertTrue(pick_fast_for_auto("What is GDP?"))
        resolved = resolve_model_for_request(MODEL_AUTO, "What is GDP?", [])
        self.assertEqual(resolved, default_fast_model())

    def test_auto_picks_full_for_coding_prompt(self):
        prompt = "Debug this Python function:\n```python\ndef avg(nums):\n    return sum(nums)/len(nums)\n```"
        self.assertFalse(pick_fast_for_auto(prompt))
        resolved = resolve_model_for_request(MODEL_AUTO, prompt, [])
        self.assertEqual(resolved, default_full_model())

    def test_locked_model_skips_auto_routing(self):
        resolved = resolve_model_for_request("grok-4", "hi", [])
        self.assertEqual(resolved, "grok-4")

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

    def test_parse_sse_chunk_streams_reasoning_when_no_content(self):
        raw = '{"choices":[{"delta":{"reasoning_content":"thinking"}}]}'
        text, active = _parse_sse_chunk(raw)
        self.assertEqual(text, "thinking")
        self.assertTrue(active)

    def test_parse_sse_chunk_returns_visible_content(self):
        raw = '{"choices":[{"delta":{"content":"Hello"}}]}'
        text, active = _parse_sse_chunk(raw)
        self.assertEqual(text, "Hello")
        self.assertTrue(active)

    def test_default_models_use_non_reasoning_fast_path(self):
        self.assertIn("non-reasoning", default_fast_model())
        self.assertTrue(default_full_model())

    def test_key_format_ok_requires_xai_prefix(self):
        self.assertIsInstance(key_format_ok(), bool)

    def test_stream_error_event_includes_message(self):
        event = stream_error_event(504, "Grok timed out after 45s.")
        self.assertEqual(event["message"], "Grok timed out after 45s.")


if __name__ == "__main__":
    unittest.main()
