from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import railway_tool


class RailwayToolTests(unittest.TestCase):
    def test_wants_railway_status_and_deploy(self):
        self.assertTrue(railway_tool.wants_railway_status("what's the railway deploy status"))
        self.assertTrue(railway_tool.wants_railway_deploy("please deploy storykeep now"))
        self.assertTrue(railway_tool.wants_railway("I set RAILWAY_API_TOKEN in variables"))
        self.assertFalse(railway_tool.wants_railway("explain python lists"))

    def test_owner_can_use_requires_token(self):
        user = type("User", (), {"email": "stevebitsko@duck.com", "is_demo_locked": False})()
        with patch.object(railway_tool, "configured", return_value=False):
            self.assertFalse(railway_tool.owner_can_use(user))
        with patch.object(railway_tool, "configured", return_value=True):
            self.assertTrue(railway_tool.owner_can_use(user))

    def test_assemble_status_tool_call(self):
        call = railway_tool.assemble_tool_call(
            [{"index": 0, "function": {"name": "railway_status", "arguments": "{}"}}]
        )
        self.assertEqual(call, {"name": "railway_status"})

    def test_fetch_status_not_configured(self):
        with patch.object(railway_tool.settings, "railway_api_token", ""):
            with patch.object(railway_tool.settings, "railway_token", ""):
                outcome = railway_tool.fetch_status()
        self.assertFalse(outcome.ok)
        self.assertIn("not set", outcome.text.lower())

    def test_format_status_for_model(self):
        outcome = railway_tool.RailwayOutcome(True, "line one")
        text = railway_tool.format_status_for_model(outcome)
        self.assertIn("Live Railway data", text)
        self.assertIn("line one", text)


if __name__ == "__main__":
    unittest.main()
