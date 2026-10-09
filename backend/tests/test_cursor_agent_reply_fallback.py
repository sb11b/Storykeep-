from __future__ import annotations

import unittest

from app.services import cursor_agent_tool
from app.services.cursor_agent_outcome import CursorAgentOutcome, summarize_agent_for_user


class CursorAgentReplyFallbackTests(unittest.TestCase):
    def test_summarize_agent_success_includes_url(self):
        outcome = CursorAgentOutcome(
            True,
            "Cursor Cloud Agent started server-side this turn:\n"
            "- Agent URL: https://cursor.com/agents/bc-123\n"
            "- Agent status: ACTIVE",
            200,
            agent_id="bc-123",
            agent_url="https://cursor.com/agents/bc-123",
        )
        text = summarize_agent_for_user(outcome)
        self.assertIn("Cursor Cloud Agent started", text)
        self.assertIn("this Storykeep chat", text)
        self.assertNotIn("https://cursor.com/agents/bc-123", text)

    def test_summarize_agent_not_configured(self):
        outcome = CursorAgentOutcome(
            False,
            cursor_agent_tool.CURSOR_OFF_APPEND.strip(),
            503,
        )
        text = summarize_agent_for_user(outcome)
        self.assertIn("CURSOR_API_KEY", text)


if __name__ == "__main__":
    unittest.main()
