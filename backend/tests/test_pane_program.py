from __future__ import annotations

import unittest

from app.services import junior_model


class PaneProgramTests(unittest.TestCase):
    def test_unnamed_junior_pane_stays_quiet(self):
        msg = "Fix the mail list contrast in frontend/src/components/mail-overlay.tsx and add tests."
        self.assertEqual(junior_model.message_program(msg), "storykeep")
        self.assertIsNone(junior_model.pane_program("Junior"))
        self.assertIsNone(junior_model.pane_program("Junior 2"))
        self.assertIsNone(junior_model.pane_mismatch_note(msg, "Junior"))

    def test_school_pane_flags_storykeep_work(self):
        msg = (
            "Fix the mail list contrast in mail-overlay.tsx.\n"
            "- Keep the orange unread dot\n"
            "Done when the list is readable."
        )
        note = junior_model.pane_mismatch_note(msg, "DAT")
        assert note is not None
        self.assertIn("named DAT", note)
        self.assertIn("StoryKeep", note)
        self.assertIn("StoryKeep pane", note)

    def test_storykeep_pane_flags_school_work(self):
        msg = "Explain the DAT homework on database normalization for my class."
        note = junior_model.pane_mismatch_note(msg, "StoryKeep")
        assert note is not None
        self.assertIn("Schoolwork", note)
        self.assertIsNone(junior_model.pane_mismatch_note(msg, "Schoolwork"))

    def test_matching_android_pane_is_quiet(self):
        msg = "The Talk/Type Compose screen should keep the Kotlin voice_id field."
        self.assertEqual(junior_model.message_program(msg), "android")
        self.assertIsNone(junior_model.pane_mismatch_note(msg, "Android"))

    def test_school_question_is_not_a_cursor_task(self):
        msg = "explain python lists and how append works for my homework"
        self.assertEqual(junior_model.message_program(msg), "school")
        self.assertIsNone(junior_model.cursor_turn_mode(msg))
