from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.services.chat_docx import text_filename
from app.services.junior_jobs import (
    JOB_RUN_CAP,
    cron_matches,
    due_this_minute,
    enforce_daily_cap,
    parse_cron,
    require_cron_secret,
)


class JuniorJobsTests(unittest.TestCase):
    def test_weekdays_cron_skips_saturday(self):
        saturday = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)
        monday = datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc)
        expr = "0 8 * * 1-5"
        self.assertFalse(cron_matches(expr, saturday))
        self.assertTrue(cron_matches(expr, monday))

    def test_parse_cron_rejects_junk(self):
        with self.assertRaises(HTTPException):
            parse_cron("every morning")

    def test_due_this_minute_skips_same_minute(self):
        now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        job = SimpleNamespace(
            enabled=True,
            timezone="UTC",
            cron="0 12 * * *",
            last_run_at=now,
        )
        self.assertFalse(due_this_minute(job, now))
        job.last_run_at = None
        self.assertTrue(due_this_minute(job, now))

    def test_daily_cap(self):
        db = MagicMock()
        db.scalar.return_value = JOB_RUN_CAP
        with self.assertRaises(HTTPException) as raised:
            enforce_daily_cap(db, uuid4())
        self.assertEqual(raised.exception.status_code, 429)

    def test_cron_secret(self):
        request = SimpleNamespace(headers={"x-junior-cron-secret": "nope", "authorization": ""})
        with patch("app.services.junior_jobs.settings") as settings:
            settings.junior_cron_secret = "s3cret"
            with self.assertRaises(HTTPException) as raised:
                require_cron_secret(request)
            self.assertEqual(raised.exception.status_code, 401)
            request.headers = {"x-junior-cron-secret": "s3cret", "authorization": ""}
            require_cron_secret(request)

    def test_text_export_names(self):
        paper = "# Grammar-fixed DAT-200 paper\n\nBody."
        self.assertEqual(text_filename(paper, "md"), "Grammar-fixed DAT-200 paper.md")
        self.assertEqual(text_filename("Just a line\n\nMore.", "txt"), "junior-note.txt")


if __name__ == "__main__":
    unittest.main()
