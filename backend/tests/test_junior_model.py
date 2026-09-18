from __future__ import annotations

import unittest

from app.services import junior_model


class JuniorModelTests(unittest.TestCase):
    def test_cap_slice_respects_message_and_token_caps(self):
        rows = [{"role": "user", "content": "x" * 2000} for _ in range(25)]
        capped, truncated = junior_model.cap_slice_messages(rows)
        self.assertLessEqual(len(capped), 20)
        self.assertTrue(truncated)

    def test_cap_slice_token_truncated_prefers_newest(self):
        rows = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "y" * 40000},
            {"role": "user", "content": "newest"},
        ]
        capped, truncated = junior_model.cap_slice_messages(rows)
        self.assertTrue(truncated)
        self.assertEqual(capped[-1]["content"], "newest")

    def test_format_index_for_model_is_slim(self):
        text = junior_model.format_index_for_model(
            [
                {
                    "id": "abc",
                    "date": "2026-09-18",
                    "title": "DAT lists",
                    "summary": "Explain Python lists",
                    "note_id": "note-1",
                    "messages": 99,
                }
            ]
        )
        self.assertIn("id=abc", text)
        self.assertIn("DAT lists", text)
        self.assertIn("Explain Python lists", text)
        self.assertNotIn("note=", text)
        self.assertNotIn("99 messages", text)

    def test_filter_standing_memory_drops_spec_sections(self):
        body = "# TIMELINE\nphase 1\n# Notes\nkeep me"
        filtered = junior_model.filter_standing_memory(body, user_text="hello")
        self.assertNotIn("TIMELINE", filtered)
        self.assertIn("keep me", filtered)

    def test_filter_standing_memory_keeps_spec_when_asked(self):
        body = "# TIMELINE\nphase 1"
        kept = junior_model.filter_standing_memory(body, user_text="read TIMELINE")
        self.assertIn("TIMELINE", kept)

    def test_model_payload_marks_truncated(self):
        payload = junior_model.model_payload(
            user_text="summarize",
            slice={"messages": [{"role": "user", "content": "hi"}], "truncated": True},
            standing_memory="mem",
        )
        self.assertIn("truncated=true", payload[0]["content"])


if __name__ == "__main__":
    unittest.main()
