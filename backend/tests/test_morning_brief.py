from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.services import morning_brief


class MorningBriefTests(unittest.TestCase):
    def test_wants_morning_phrases(self):
        for msg in (
            "what's on today",
            "Whats on today",
            "what is due today",
            "school morning",
            "morning line",
            "today's school",
        ):
            self.assertTrue(morning_brief.wants_morning(msg), msg)
        self.assertFalse(morning_brief.wants_morning("what is on the calendar next week"))
        self.assertFalse(morning_brief.wants_morning("explain python lists for my homework"))

    def test_format_includes_three_sections(self):
        text = morning_brief.format_morning(
            date_label="Thursday, September 24",
            events=[{"title": "DAT class", "start": "2026-09-24T13:00:00+00:00"}],
            calendar_connected=True,
            mail_items=[{"from": "Ada", "subject": "Syllabus"}],
            mail_total=10,
            mail_connected=True,
            notes=[("Normalization", "DAT"), ("Bare note", None)],
        )
        self.assertIn("School morning — Thursday, September 24", text)
        self.assertIn("Today", text)
        self.assertIn("DAT class", text)
        self.assertIn("9:00 am", text)
        self.assertIn("Unread mail", text)
        self.assertIn("Ada — Syllabus", text)
        self.assertIn("9 more unread", text)
        self.assertIn("Pinned Schoolwork", text)
        self.assertIn("Normalization (DAT)", text)
        self.assertIn("- Bare note", text)
        self.assertNotIn("preview", text.lower())

    def test_missing_connections_are_named(self):
        text = morning_brief.format_morning(
            date_label="Thursday, September 24",
            events=[],
            calendar_connected=False,
            mail_items=[],
            mail_connected=False,
            notes=[],
        )
        self.assertIn("Open Calendar", text)
        self.assertIn("Open Mail", text)
        self.assertIn("No pinned notes", text)

    def test_today_window_is_eastern(self):
        # 03:30 UTC is still the previous evening in New York during September (EDT, UTC-4).
        now = datetime(2026, 9, 24, 3, 30, tzinfo=timezone.utc)
        start, end, label = morning_brief.today_window(now)
        self.assertEqual(label, "Wednesday, September 23")
        self.assertEqual(start.hour, 0)
        self.assertEqual((end - start).days, 1)
