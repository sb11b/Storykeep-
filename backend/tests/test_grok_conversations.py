from __future__ import annotations

import unittest
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException

from app.services.chat import build_xai_messages, thread_window, validate_payload
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

    def test_validate_payload_accepts_windowed_history(self):
        history = [{"role": "user", "content": f"m{index}"} for index in range(30)]
        windowed = thread_window(history)
        cleaned = validate_payload(windowed)
        self.assertEqual(cleaned[-1]["role"], "user")


if __name__ == "__main__":
    unittest.main()
