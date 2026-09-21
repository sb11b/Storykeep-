from __future__ import annotations

import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.services.junior_stamp import format_junior_bubble_stamp, stamp_assistant_content


class JuniorStampTests(unittest.TestCase):
    def test_format_stamp_utc_and_eastern(self):
        when = datetime(2026, 1, 15, 18, 4, tzinfo=timezone.utc)
        line = format_junior_bubble_stamp(when)
        self.assertEqual(line, "UTC: 2026-01-15 18:04    ET (EST): 2026-01-15 13:04")

    def test_format_stamp_edt_in_summer(self):
        when = datetime(2026, 7, 4, 16, 30, tzinfo=timezone.utc)
        line = format_junior_bubble_stamp(when)
        eastern = when.astimezone(ZoneInfo("America/New_York"))
        self.assertIn(f"ET ({eastern.tzname()}):", line)
        self.assertIn("2026-07-04 12:30", line)

    def test_stamp_assistant_content_prepends_line(self):
        body = "GitHub status snapshot."
        stamped = stamp_assistant_content(body, now=datetime(2026, 9, 21, 7, 10, tzinfo=timezone.utc))
        self.assertTrue(stamped.startswith("UTC: 2026-09-21 07:10    ET ("))
        self.assertIn("\nGitHub status snapshot.", stamped)

    def test_stamp_assistant_content_skips_empty(self):
        self.assertEqual(stamp_assistant_content(""), "")
        self.assertEqual(stamp_assistant_content("   "), "")

    def test_stamp_assistant_content_does_not_double_stamp(self):
        head = "UTC: 2026-09-21 07:10    ET (EDT): 2026-09-21 03:10"
        body = f"{head}\nAlready stamped."
        self.assertEqual(stamp_assistant_content(body), body)


if __name__ == "__main__":
    unittest.main()
