from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.services.studio import extract_json_object, next_run_at, parse_patches, parse_plan, sanitize_path


class StudioServiceTests(unittest.TestCase):
    def test_weekday_schedule_skips_weekend(self):
        # Saturday 10:00 America/New_York
        after = datetime(2026, 9, 12, 14, 0, tzinfo=timezone.utc)
        nxt = next_run_at(
            trigger="schedule",
            schedule="weekdays",
            hour=8,
            minute=0,
            weekday=0,
            monthday=1,
            tz_name="America/New_York",
            after=after,
        )
        self.assertIsNotNone(nxt)
        local = nxt.astimezone(timezone.utc)
        self.assertEqual(local.weekday(), 0)

    def test_email_trigger_has_no_next_run(self):
        self.assertIsNone(
            next_run_at(
                trigger="email",
                schedule="daily",
                hour=8,
                minute=0,
                weekday=0,
                monthday=1,
                tz_name="UTC",
            )
        )

    def test_parse_plan_and_patches(self):
        plan_text = '{"plan":[{"id":"1","title":"Read hello.py","detail":"See greet"}]}'
        self.assertEqual(parse_plan(plan_text)[0]["title"], "Read hello.py")
        build = """done\n```json\n{"patches":[{"path":"src/hello.py","content":"print(1)\\n"}]}\n```"""
        patches = parse_patches(build)
        self.assertEqual(patches[0]["path"], "src/hello.py")
        self.assertIn("print(1)", patches[0]["content"])

    def test_sanitize_path_blocks_parent(self):
        with self.assertRaises(Exception):
            sanitize_path("../secret")
        self.assertEqual(sanitize_path("src/hello.py"), "src/hello.py")

    def test_extract_json_object_from_prose(self):
        parsed = extract_json_object('Here you go {"plan":[{"title":"A","detail":"B"}]} thanks')
        self.assertEqual(parsed["plan"][0]["title"], "A")


if __name__ == "__main__":
    unittest.main()
