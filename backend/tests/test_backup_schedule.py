from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.services.backup import run_scheduled_s3_dumps, scheduled_s3_dump_due


class ScheduledS3DumpTests(unittest.TestCase):
    def test_due_when_never_dumped(self):
        now = datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc)
        self.assertTrue(scheduled_s3_dump_due(now, None, 24))

    def test_not_due_inside_interval(self):
        now = datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc)
        last = now - timedelta(hours=3)
        self.assertFalse(scheduled_s3_dump_due(now, last, 24))

    def test_due_after_interval(self):
        now = datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc)
        last = now - timedelta(hours=24)
        self.assertTrue(scheduled_s3_dump_due(now, last, 24))

    def test_disabled_when_interval_zero(self):
        now = datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc)
        self.assertFalse(scheduled_s3_dump_due(now, None, 0))

    def test_run_skips_without_object_store(self):
        with (
            patch("app.services.backup.object_store_ready", return_value=False),
            patch("app.services.backup.create_db_dump") as dump,
        ):
            run_scheduled_s3_dumps()
            dump.assert_not_called()

    def test_run_dumps_when_due_and_store_ready(self):
        db = MagicMock()
        with (
            patch("app.services.backup.settings") as settings,
            patch("app.services.backup.object_store_ready", return_value=True),
            patch("app.services.backup.SessionLocal", return_value=db),
            patch("app.services.backup.last_successful_s3_dump_at", return_value=None),
            patch("app.services.backup.create_db_dump") as dump,
        ):
            settings.backup_interval_hours = 24
            run_scheduled_s3_dumps()
            dump.assert_called_once_with(db, None)
            db.close.assert_called_once()

    def test_run_skips_when_recent_s3_dump_exists(self):
        db = MagicMock()
        last = datetime.now(timezone.utc)
        with (
            patch("app.services.backup.settings") as settings,
            patch("app.services.backup.object_store_ready", return_value=True),
            patch("app.services.backup.SessionLocal", return_value=db),
            patch("app.services.backup.last_successful_s3_dump_at", return_value=last),
            patch("app.services.backup.create_db_dump") as dump,
        ):
            settings.backup_interval_hours = 24
            run_scheduled_s3_dumps()
            dump.assert_not_called()
            db.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
