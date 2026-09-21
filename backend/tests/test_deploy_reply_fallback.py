from __future__ import annotations

import unittest

from app.services import chat, junior_model, railway_tool


class DeployReplyFallbackTests(unittest.TestCase):
    def test_ops_deploy_turn_uses_xhigh_on_auto(self):
        msg = "Deploy Storykeep to Railway."
        self.assertTrue(junior_model.is_ops_turn(msg))
        self.assertTrue(railway_tool.wants_railway_deploy(msg))
        self.assertTrue(chat.pick_xhigh_for_auto(msg))
        self.assertEqual(chat.resolve_reasoning_for_request(chat.MODEL_AUTO, "auto", msg, []), "xhigh")

    def test_summarize_deploy_success(self):
        outcome = railway_tool.RailwayOutcome(
            True,
            "Railway deploy for storykeep in production.\n"
            "Deployment id: dep-123\n"
            "Final status: SUCCESS\nURL: https://storykeep-production.up.railway.app",
            200,
        )
        text = railway_tool.summarize_deploy_for_user(outcome)
        self.assertIn("finished", text.lower())
        self.assertIn("dep-123", text)
        self.assertIn("storykeep-production", text)


if __name__ == "__main__":
    unittest.main()
