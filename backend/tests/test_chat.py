from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi import HTTPException

from app.services.chat import enforce_rate_limit, validate_payload, _rate_hits


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
