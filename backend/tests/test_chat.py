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
            validate_payload([{"role": "user", "content": "x" * 9000}])
        cleaned = validate_payload([{"role": "user", "content": "What is this about?"}])
        self.assertEqual(cleaned[0]["role"], "user")

    def test_excerpt_is_capped(self):
        from types import SimpleNamespace
        from app.services.chat import article_excerpt

        article = SimpleNamespace(title="Long", content_text="word " * 8000, content_html=None, summary=None)
        excerpt = article_excerpt(article)
        self.assertLessEqual(len(excerpt), 12_000 + 80)
        self.assertIn("Title: Long", excerpt)
        self.assertTrue(excerpt.endswith("…"))

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

    def test_article_mode_includes_excerpt(self):
        excerpt = "Title: Demo\n\nBody text"
        messages = build_xai_messages([{"role": "user", "content": "Summarize"}], excerpt, include_article=True)
        system = messages[0]["content"]
        self.assertIn("Current article excerpt", system)
        self.assertIn("Body text", system)

    def test_thread_window_limits_context(self):
        history = [{"role": "user", "content": f"line {index}"} for index in range(20)]
        windowed = thread_window(history, limit=6)
        self.assertEqual(len(windowed), 6)
        self.assertEqual(windowed[-1]["content"], "line 19")

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


if __name__ == "__main__":
    unittest.main()
