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

    def test_local_merge_conflict_does_not_start_an_agent(self):
        msg = (
            "need to fix errors\n"
            "README.md: needs merge\n"
            "error: you need to resolve your current index first\n"
            "error: Pulling is not possible because you have unmerged files.\n"
            "go ahead and start next step\n"
            "pack-reused 0 (from 0)\n"
        )
        self.assertFalse(cursor_agent_tool.wants_start(msg))
        reply = cursor_agent_tool.local_merge_repair(msg)
        assert reply is not None
        self.assertIn("git merge --abort", reply)
        self.assertIn("git reset --hard github/main", reply)
        self.assertIn("Do not push", reply)
        self.assertIsNone(cursor_agent_tool.local_merge_repair("go ahead and start next step"))
        asked = cursor_agent_tool.local_merge_repair(
            "correct the error then give me a paste for ubantu"
        )
        assert asked is not None
        self.assertIn("git merge --abort", asked)
        self.assertIn("git reset --hard github/main", asked)
        self.assertFalse(cursor_agent_tool.wants_start("correct the error then give me a paste for ubantu"))

    def test_extract_branch_ignores_git_pack_line(self):
        msg = (
            "go ahead and start next step\n"
            "pack-reused 0 (from 0)\n"
            "From https://github.com/sb11b/Storykeep-\n"
            "Branch from current GitHub main"
        )
        self.assertEqual(cursor_agent_tool.extract_branch(msg), "main")

    def test_wants_start_ignores_negated_phrase(self):
        msg = "Junior, this already happened. Do not start a Cursor agent for it."
        self.assertFalse(cursor_agent_tool.wants_start(msg))

    def test_sequenced_polish_starts_on_main(self):
        msg = "go ahead and start sequenced #2 polish"
        self.assertTrue(cursor_agent_tool.wants_start(msg))
        self.assertEqual(cursor_agent_tool.extract_branch(msg), "main")
        task = cursor_agent_tool.polish_2_task(msg)
        self.assertIsNotNone(task)
        assert task is not None
        self.assertIn("sb11b/Storykeep-", task)
        self.assertIn("junior-mobile", task)
        self.assertNotIn("no working create path", task.lower())

    def test_send_next_step_starts_sequenced_four(self):
        msg = "lets go ahead and send the next step"
        self.assertTrue(cursor_agent_tool.wants_start(msg))
        self.assertEqual(cursor_agent_tool.extract_branch(msg), "main")
        task = cursor_agent_tool.next_step_task(msg)
        self.assertIsNotNone(task)
        assert task is not None
        self.assertIn("Sequenced #22", task)
        self.assertNotIn("cannot start an agent", task.lower())
        self.assertNotIn("isn't defined", task.lower())
        self.assertFalse(cursor_agent_tool.wants_start("do not send the next step"))
        self.assertIsNone(cursor_agent_tool.next_step_task("do not send the next step"))
        six = cursor_agent_tool.next_step_task("go ahead and start sequence # 6")
        assert six is not None
        self.assertIn("Sequenced #6", six)
        self.assertIn("junior-client-queue-multi-v1", six)
        seven = cursor_agent_tool.next_step_task("go ahead and start sequenced #7")
        assert seven is not None
        self.assertIn("Sequenced #7", seven)
        self.assertIn("junior-client-context-page-v1", seven)
        eight = cursor_agent_tool.next_step_task("go ahead and start sequenced #8")
        assert eight is not None
        self.assertIn("Sequenced #8", eight)
        self.assertIn("junior-client-agents-page-v1", eight)
        nine = cursor_agent_tool.next_step_task("go ahead and start sequenced #9")
        assert nine is not None
        self.assertIn("Sequenced #9", nine)
        self.assertIn("junior-client-memory-write-v1", nine)
        ten = cursor_agent_tool.next_step_task("go ahead and start sequenced #10")
        assert ten is not None
        self.assertIn("Sequenced #10", ten)
        self.assertIn("junior-client-sessions-page-v1", ten)
        eleven = cursor_agent_tool.next_step_task("go ahead and start sequenced #11")
        assert eleven is not None
        self.assertIn("Sequenced #11", eleven)
        self.assertIn("junior-client-thread-get-v1", eleven)
        twelve = cursor_agent_tool.next_step_task("go ahead and start sequenced #12")
        assert twelve is not None
        self.assertIn("Sequenced #12", twelve)
        self.assertIn("junior-client-memory-get-v1", twelve)
        thirteen = cursor_agent_tool.next_step_task("go ahead and start sequenced #13")
        assert thirteen is not None
        self.assertIn("Sequenced #13", thirteen)
        self.assertIn("junior-client-agent-get-v1", thirteen)
        fourteen = cursor_agent_tool.next_step_task("go ahead and start sequenced #14")
        assert fourteen is not None
        self.assertIn("Sequenced #14", fourteen)
        self.assertIn("junior-client-session-get-v1", fourteen)
        fifteen = cursor_agent_tool.next_step_task("go ahead and start sequenced #15")
        assert fifteen is not None
        self.assertIn("Sequenced #15", fifteen)
        self.assertIn("junior-client-message-get-v1", fifteen)
        sixteen = cursor_agent_tool.next_step_task("go ahead and start sequenced #16")
        assert sixteen is not None
        self.assertIn("Sequenced #16", sixteen)
        self.assertIn("junior-client-project-get-v1", sixteen)
        seventeen = cursor_agent_tool.next_step_task("go ahead and start sequenced #17")
        assert seventeen is not None
        self.assertIn("Sequenced #17", seventeen)
        self.assertIn("junior-client-search-get-v1", seventeen)
        eighteen = cursor_agent_tool.next_step_task("go ahead and start sequenced #18")
        assert eighteen is not None
        self.assertIn("Sequenced #18", eighteen)
        self.assertIn("junior-client-context-get-v1", eighteen)
        nineteen = cursor_agent_tool.next_step_task("go ahead and start sequenced #19")
        assert nineteen is not None
        self.assertIn("Sequenced #19", nineteen)
        self.assertIn("junior-client-thread-message-get-v1", nineteen)
        twenty = cursor_agent_tool.next_step_task("go ahead and start sequenced #20")
        assert twenty is not None
        self.assertIn("Sequenced #20", twenty)
        self.assertIn("junior-client-continue-get-v1", twenty)
        twenty_one = cursor_agent_tool.next_step_task("go ahead and start sequenced #21")
        assert twenty_one is not None
        self.assertIn("Sequenced #21", twenty_one)
        self.assertIn("junior-client-project-agent-get-v1", twenty_one)

    def test_sequence_number_five_starts(self):
        msg = "go ahead and start Sequence number five."
        self.assertTrue(cursor_agent_tool.wants_start(msg))
        self.assertEqual(cursor_agent_tool.sequence_number(msg), 5)
        self.assertEqual(cursor_agent_tool.extract_branch(msg), "main")
        task = cursor_agent_tool.sequenced_task(msg)
        assert task is not None
        self.assertIn("Sequenced #5", task)
        self.assertIn("last_failed_post", task)
        self.assertFalse(cursor_agent_tool.wants_start("do not start sequence number five"))
        self.assertTrue(cursor_agent_tool.wants_start("start next step"))
        four = cursor_agent_tool.next_step_task("sequenced #4")
        assert four is not None
        self.assertIn("Sequenced #4", four)
        six = cursor_agent_tool.sequenced_task("go ahead and start sequence # 6")
        assert six is not None
        self.assertIn("Sequenced #6", six)
        self.assertIn("junior-client-queue-multi-v1", six)
        seven = cursor_agent_tool.sequenced_task("sequenced #7")
        assert seven is not None
        self.assertIn("Sequenced #7", seven)
        self.assertIn("junior-client-context-page-v1", seven)
        eight = cursor_agent_tool.sequenced_task("sequenced #8")
        assert eight is not None
        self.assertIn("Sequenced #8", eight)
        self.assertIn("junior-client-agents-page-v1", eight)
        nine = cursor_agent_tool.sequenced_task("sequenced #9")
        assert nine is not None
        self.assertIn("Sequenced #9", nine)
        self.assertIn("junior-client-memory-write-v1", nine)
        ten = cursor_agent_tool.sequenced_task("sequenced #10")
        assert ten is not None
        self.assertIn("Sequenced #10", ten)
        self.assertIn("junior-client-sessions-page-v1", ten)
        eleven = cursor_agent_tool.sequenced_task("sequenced #11")
        assert eleven is not None
        self.assertIn("Sequenced #11", eleven)
        self.assertIn("junior-client-thread-get-v1", eleven)
        twelve = cursor_agent_tool.sequenced_task("sequenced #12")
        assert twelve is not None
        self.assertIn("Sequenced #12", twelve)
        self.assertIn("junior-client-memory-get-v1", twelve)
        thirteen = cursor_agent_tool.sequenced_task("sequenced #13")
        assert thirteen is not None
        self.assertIn("Sequenced #13", thirteen)
        self.assertIn("junior-client-agent-get-v1", thirteen)
        fourteen = cursor_agent_tool.sequenced_task("sequenced #14")
        assert fourteen is not None
        self.assertIn("Sequenced #14", fourteen)
        self.assertIn("junior-client-session-get-v1", fourteen)
        fifteen = cursor_agent_tool.sequenced_task("sequenced #15")
        assert fifteen is not None
        self.assertIn("Sequenced #15", fifteen)
        self.assertIn("junior-client-message-get-v1", fifteen)
        sixteen = cursor_agent_tool.sequenced_task("sequenced #16")
        assert sixteen is not None
        self.assertIn("Sequenced #16", sixteen)
        self.assertIn("junior-client-project-get-v1", sixteen)
        seventeen = cursor_agent_tool.sequenced_task("sequenced #17")
        assert seventeen is not None
        self.assertIn("Sequenced #17", seventeen)
        self.assertIn("junior-client-search-get-v1", seventeen)
        eighteen = cursor_agent_tool.sequenced_task("sequenced #18")
        assert eighteen is not None
        self.assertIn("Sequenced #18", eighteen)
        self.assertIn("junior-client-context-get-v1", eighteen)
        nineteen = cursor_agent_tool.sequenced_task("sequenced #19")
        assert nineteen is not None
        self.assertIn("Sequenced #19", nineteen)
        self.assertIn("junior-client-thread-message-get-v1", nineteen)
        twenty = cursor_agent_tool.sequenced_task("sequenced #20")
        assert twenty is not None
        self.assertIn("Sequenced #20", twenty)
        self.assertIn("junior-client-continue-get-v1", twenty)
        twenty_one = cursor_agent_tool.sequenced_task("sequenced #21")
        assert twenty_one is not None
        self.assertIn("Sequenced #21", twenty_one)
        self.assertIn("junior-client-project-agent-get-v1", twenty_one)

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
