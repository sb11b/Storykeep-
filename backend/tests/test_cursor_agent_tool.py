from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.services import cursor_agent_tool, junior_model


class CursorAgentToolTests(unittest.TestCase):
    def test_wants_start_matches_explicit_phrases(self):
        for msg in (
            "Start a cursor agent to add Railway deploy polling tests",
            "Launch cloud agent on main to fix chat router",
            "Run this in a cursor agent: refactor junior_model extras",
            "Open a Cloud Agent task for the STT draft race",
        ):
            self.assertTrue(cursor_agent_tool.wants_start(msg), msg)

    def test_wants_start_not_prompt_generation(self):
        msg = "write a prompt for cursor to fix login"
        self.assertFalse(cursor_agent_tool.wants_start(msg))
        self.assertEqual(junior_model.cursor_turn_mode(msg), "generate")

    def test_delegate_turn_blocks_cursor_follow_mode(self):
        msg = (
            "Start a cursor agent to fix the STT draft race in grok-pane "
            "use draftValueRef on send add tests done when send includes mic transcript"
        )
        self.assertTrue(junior_model.is_delegate_turn(msg))
        self.assertIsNone(junior_model.cursor_turn_mode(msg))

    def test_extract_prompt_strips_prefix(self):
        raw = "Start a cursor agent to: add tests for railway deploy polling"
        self.assertEqual(
            cursor_agent_tool.extract_prompt(raw),
            "add tests for railway deploy polling",
        )

    def test_extract_branch_from_message(self):
        msg = "Launch cloud agent from develop to fix auth"
        self.assertEqual(cursor_agent_tool.extract_branch(msg), "develop")

    def test_extract_branch_on_main(self):
        msg = "Launch cloud agent on main to fix auth"
        self.assertEqual(cursor_agent_tool.extract_branch(msg), "main")

    def test_extract_branch_ignores_on_a_article(self):
        msg = (
            "Start a cursor agent on a new branch to scaffold the Android module "
            "days 1-3 Kotlin Compose min SDK 26"
        )
        self.assertEqual(cursor_agent_tool.extract_branch(msg), "main")

    def test_extract_branch_explicit(self):
        msg = "Start cursor agent branch feature/android-voice on main repo"
        self.assertEqual(cursor_agent_tool.extract_branch(msg), "feature/android-voice")

    def test_extract_branch_ignores_storykeep_product_name(self):
        msg = (
            "Shared Junior memory is live on StoryKeep production. "
            "Start a cursor agent to record that the tables exist."
        )
        self.assertEqual(cursor_agent_tool.extract_branch(msg), "main")

    def test_wants_start_ignores_negated_phrase(self):
        msg = "Junior, this already happened. Do not start a Cursor agent for it."
        self.assertFalse(cursor_agent_tool.wants_start(msg))

    @patch("app.services.cursor_agent_tool.httpx.Client")
    @patch("app.services.cursor_agent_tool.settings")
    def test_start_agent_success(self, mock_settings: MagicMock, mock_client_cls: MagicMock) -> None:
        mock_settings.cursor_api_key = "key_test"
        mock_settings.cursor_agent_repo = ""
        mock_settings.github_repo = "sb11b/Storykeep-"
        mock_settings.cursor_agent_branch = "main"
        mock_settings.cursor_api_url = "https://api.cursor.com"
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "agent": {
                "id": "bc-00000000-0000-0000-0000-000000000001",
                "name": "Add tests",
                "status": "ACTIVE",
                "url": "https://cursor.com/agents/bc-00000000-0000-0000-0000-000000000001",
            },
            "run": {"id": "run-1", "status": "CREATING"},
        }
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.request.return_value = response
        mock_client_cls.return_value = mock_client

        outcome = cursor_agent_tool.start_agent("Add deploy polling tests", branch="main")
        self.assertTrue(outcome.ok)
        self.assertIn("Agent URL:", outcome.text)
        self.assertIn("Push to main (Ubuntu)", outcome.text)
        self.assertEqual(outcome.agent_id, "bc-00000000-0000-0000-0000-000000000001")
        payload = mock_client.request.call_args.kwargs["json"]
        self.assertEqual(payload["prompt"]["text"], "Add deploy polling tests")
        self.assertEqual(payload["repos"][0]["startingRef"], "main")

    def test_push_workflow_mentions_cursor_branch(self):
        text = cursor_agent_tool.push_workflow_for_user(
            agent_url="https://cursor.com/agents/bc-test",
            repo_slug="sb11b/Storykeep-",
        )
        self.assertIn("cursor/*", text)
        self.assertIn("git fetch github", text)
        self.assertIn("Open in Cursor", text)

    @patch("app.services.cursor_agent_tool.httpx.Client")
    @patch("app.services.cursor_agent_tool.settings")
    def test_start_agent_delegate_auto_pr(self, mock_settings: MagicMock, mock_client_cls: MagicMock) -> None:
        mock_settings.cursor_api_key = "key_test"
        mock_settings.cursor_agent_repo = ""
        mock_settings.github_repo = "sb11b/Storykeep-"
        mock_settings.cursor_agent_branch = "main"
        mock_settings.cursor_api_url = "https://api.cursor.com"
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "agent": {"id": "bc-1", "status": "ACTIVE", "url": "https://cursor.com/agents/bc-1"},
            "run": {"id": "run-1", "status": "CREATING"},
        }
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.request.return_value = response
        mock_client_cls.return_value = mock_client
        outcome = cursor_agent_tool.start_agent("Task", branch="main", auto_create_pr=True)
        self.assertTrue(outcome.ok)
        self.assertIn("Auto PR", outcome.text)
        self.assertTrue(mock_client.request.call_args.kwargs["json"].get("autoCreatePR"))

    @patch("app.services.cursor_agent_tool.settings")
    def test_start_agent_not_configured(self, mock_settings: MagicMock) -> None:
        mock_settings.cursor_api_key = ""
        outcome = cursor_agent_tool.start_agent("Do something")
        self.assertFalse(outcome.ok)
        self.assertIn("CURSOR_API_KEY", outcome.text)


if __name__ == "__main__":
    unittest.main()
