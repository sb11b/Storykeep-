from __future__ import annotations

import unittest
from uuid import uuid4

from fastapi import HTTPException

from app.config import settings
from app.services.stt_limits import clear_stt_rate_limits, enforce_stt_rate_limit


class SttLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_stt_rate_limits()

    def test_rate_limit_caps_hourly_sessions(self):
        user = uuid4()
        now = 1_700_000_000.0
        limit = int(settings.stt_sessions_per_hour or 60)
        for index in range(limit):
            enforce_stt_rate_limit(user, now=now + index)
        with self.assertRaises(HTTPException) as caught:
            enforce_stt_rate_limit(user, now=now + limit + 1)
        self.assertEqual(caught.exception.status_code, 429)
        enforce_stt_rate_limit(user, now=now + 3601)


if __name__ == "__main__":
    unittest.main()
