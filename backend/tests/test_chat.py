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

    def test_rate_limit(self):
        user = uuid4()
        now = 1_700_000_000.0
        for index in range(30):
            enforce_rate_limit(user, now=now + index)
        with self.assertRaises(HTTPException) as caught:
            enforce_rate_limit(user, now=now + 31)
        self.assertEqual(caught.exception.status_code, 429)
        enforce_rate_limit(user, now=now + 3601)


if __name__ == "__main__":
    unittest.main()
