from __future__ import annotations

import unittest

from app.services import cursor_agent_tool


class CursorAgentReplyFallbackTests(unittest.TestCase):
    def test_summarize_agent_success_includes_url(self):
        outcome = cursor_agent_tool.CursorAgentOutcome(
            True,
            "Cursor Cloud Agent started server-side this turn:\n"
            "- Agent URL: https://cursor.com/agents/bc-123\n"
            "- Agent status: ACTIVE",
            200,
            agent_id="bc-123",
            agent_url="https://cursor.com/agents/bc-123",
        )
        text = cursor_agent_tool.summarize_agent_for_user(outcome)
        self.assertIn("Cursor Cloud Agent started", text)
        self.assertIn("https://cursor.com/agents/bc-123", text)

    def test_summarize_agent_not_configured(self):
        outcome = cursor_agent_tool.CursorAgentOutcome(
            False,
            cursor_agent_tool.CURSOR_OFF_APPEND.strip(),
            503,
        )
        text = cursor_agent_tool.summarize_agent_for_user(outcome)
        self.assertIn("CURSOR_API_KEY", text)


if __name__ == "__main__":
    unittest.main()
