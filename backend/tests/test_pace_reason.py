from __future__ import annotations

import unittest

from app.services.chat import pace_reason


class PaceReasonTests(unittest.TestCase):
    def test_short_chat_stays_fast(self):
        text = pace_reason("hello", "low", "auto")
        self.assertIn("Fast turn", text)
        self.assertIn("low", text)

    def test_manual_xhigh_on_a_short_line_explains_the_clamp(self):
        text = pace_reason("hello", "low", "xhigh")
        self.assertIn("Fast turn", text)
        self.assertIn("stays on low", text)

    def test_school_turn_explains_xhigh(self):
        message = "This is a long homework assignment for DAT-325. " * 8
        text = pace_reason(message, "xhigh", "auto")
        self.assertIn("Slow turn", text)
        self.assertIn("school or code", text)

    def test_manual_high_says_the_dropdown(self):
        text = pace_reason("Tell me about the reading.", "high", "high")
        self.assertIn("Slow turn", text)
        self.assertIn("You set Reasoning to high", text)

    def test_cursor_start_explains_the_agent(self):
        text = pace_reason("start a cursor agent to fix the mail list", "xhigh", "auto")
        self.assertIn("Cloud Agent", text)
