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

    def test_deploy_not_triggered_for_android_or_build_junior(self):
        self.assertFalse(railway_tool.wants_railway_deploy("build Junior with Compose and SkColor"))
        self.assertFalse(
            railway_tool.wants_railway_deploy(
                "triggering a Railway deploy since you asked to build Junior from this chat"
            )
        )
        self.assertFalse(railway_tool.wants_railway_deploy("run server/schema.sql on Railway Postgres"))
        self.assertTrue(railway_tool.wants_railway_deploy("deploy storykeep to railway now"))

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


    def test_poll_deployment_success(self):
        calls = iter(
            [
                {"id": "d1", "status": "BUILDING", "staticUrl": ""},
                {"id": "d1", "status": "SUCCESS", "staticUrl": "https://storykeep-production.up.railway.app"},
            ]
        )

        def fake_fetch(_deployment_id: str):
            return next(calls)

        with patch.object(railway_tool, "fetch_deployment", side_effect=fake_fetch):
            with patch.object(railway_tool.time, "sleep"):
                with patch.object(railway_tool.time, "monotonic", side_effect=[0.0, 1.0, 2.0]):
                    status, detail, ok = railway_tool.poll_deployment("d1")
        self.assertTrue(ok)
        self.assertEqual(status, "SUCCESS")
        self.assertIn("SUCCESS", detail)


if __name__ == "__main__":
    unittest.main()
