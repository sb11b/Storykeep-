from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services import cursor_agent_tool, junior_memory
from app.services.cursor_agent_tool import AgentRunSnapshot
from app.services.cursor_agent_watch import poll_one


class AgentFollowUpTests(unittest.TestCase):
    def test_finished_follow_up_names_the_branch(self):
        text = cursor_agent_tool.format_follow_up(
            AgentRunSnapshot(
                "FINISHED",
                "Fixed the mail list contrast and pin order.",
                "cursor/mail-pin",
                "https://github.com/sb11b/Storykeep-/pull/12",
            ),
            agent_url="https://cursor.com/agents/bc-1",
        )
        self.assertIsNotNone(text)
        assert text is not None
        self.assertIn("Cloud Agent update", text)
        self.assertIn("git merge --abort", text)
        self.assertIn("git reset --hard github/main", text)
        self.assertIn("git merge --ff-only github/cursor/mail-pin", text)
        self.assertIn("What changed: Fixed the mail list contrast", text)
        self.assertIn("pull/12", text)
        self.assertIn("The result is in this chat", text)
        self.assertNotIn("https://cursor.com/agents/bc-1", text)
        self.assertNotIn("YOUR-BRANCH-NAME", text)

    def test_running_follow_up_is_empty(self):
        self.assertIsNone(
            cursor_agent_tool.format_follow_up(AgentRunSnapshot("RUNNING"), agent_url="https://cursor.com/agents/bc-1")
        )

    def test_error_follow_up_stops_the_wait(self):
        text = cursor_agent_tool.format_follow_up(
            AgentRunSnapshot("ERROR", "boom"),
            agent_url="https://cursor.com/agents/bc-1",
        )
        assert text is not None
        self.assertIn("status ERROR", text)
        self.assertNotIn("git merge", text)

    @patch(
        "app.services.cursor_agent_watch.cursor_agent_bugbot.bugbot_section",
        return_value=(
            "Review analytics\n\nPosted review\nCommit: 9f3c2a1b7d8e\nFindings: 2\nCost: 42.5 cents\n"
            "1. high — resolved — comment 2147483999",
            True,
        ),
    )
    @patch("app.services.github_tool.open_pull_request", return_value="https://github.com/sb11b/Storykeep-/pull/99")
    @patch("app.services.cursor_agent_watch.grok_store.append_message")
    @patch("app.services.cursor_agent_watch.grok_store.lookup_owned_conversation")
    @patch("app.services.cursor_agent_watch.cursor_agent_tool.fetch_run")
    def test_poll_posts_once(self, fetch_run, lookup, append_message, open_pull_request, bugbot_section):
        fetch_run.return_value = AgentRunSnapshot("FINISHED", "Done.", "cursor/mail-pin", None, "run-1")
        lookup.return_value = SimpleNamespace(id=uuid.uuid4())
        row = SimpleNamespace(
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            agent_id="bc-1",
            run_id=None,
            agent_url="https://cursor.com/agents/bc-1",
            starting_branch="main",
            status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
        )
        poll_one(MagicMock(), row)
        self.assertEqual(row.status, "posted")
        self.assertEqual(row.run_id, "run-1")
        content = append_message.call_args.kwargs["content"]
        self.assertIn("git merge --abort", content)
        self.assertIn("git merge --ff-only github/cursor/mail-pin", content)
        self.assertIn("pull/99", content)
        self.assertIn("Review analytics", content)
        self.assertIn("Commit: 9f3c2a1b7d8e", content)
        self.assertIn("comment 2147483999", content)
        open_pull_request.assert_called_once()
        bugbot_section.assert_called_once()

    @patch("app.services.cursor_agent_watch.grok_store.append_message")
    @patch("app.services.cursor_agent_watch.grok_store.lookup_owned_conversation")
    @patch("app.services.cursor_agent_watch.cursor_agent_tool.fetch_run")
    def test_stale_running_posts_a_still_going_note(self, fetch_run, lookup, append_message):
        fetch_run.return_value = AgentRunSnapshot("RUNNING")
        lookup.return_value = SimpleNamespace(id=uuid.uuid4())
        row = SimpleNamespace(
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            agent_id="bc-1",
            run_id="run-1",
            agent_url="https://cursor.com/agents/bc-1",
            starting_branch="main",
            status="pending",
            created_at=datetime.now(timezone.utc) - timedelta(hours=4),
            updated_at=None,
        )
        poll_one(MagicMock(), row)
        self.assertEqual(row.status, "posted")
        self.assertIn("still going", append_message.call_args.kwargs["content"])

    @patch("app.services.cursor_agent_watch.cursor_agent_bugbot.bugbot_section", return_value=("", False))
    @patch("app.services.github_tool.open_pull_request", return_value="https://github.com/sb11b/Storykeep-/pull/99")
    @patch("app.services.cursor_agent_watch.grok_store.append_message")
    @patch("app.services.cursor_agent_watch.grok_store.lookup_owned_conversation")
    @patch("app.services.cursor_agent_watch.cursor_agent_tool.fetch_run")
    def test_finished_agent_waits_for_bugbot(self, fetch_run, lookup, append_message, open_pull_request, _bugbot):
        fetch_run.return_value = AgentRunSnapshot("FINISHED", "Done.", "cursor/mail-pin", None, "run-1")
        lookup.return_value = SimpleNamespace(id=uuid.uuid4())
        row = SimpleNamespace(
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            agent_id="bc-1",
            run_id=None,
            agent_url="",
            starting_branch="main",
            status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
        )
        poll_one(MagicMock(), row)
        self.assertEqual(row.status, "posted")
        self.assertIn("Finished.", append_message.call_args.kwargs["content"])
        self.assertNotIn("Review analytics", append_message.call_args.kwargs["content"])
        self.assertNotIn("has not finished", append_message.call_args.kwargs["content"])
        open_pull_request.assert_called_once()
        self.assertIn("Bugbot is off", open_pull_request.call_args.kwargs["body"])

    @patch(
        "app.services.cursor_agent_watch.cursor_agent_bugbot.bugbot_section",
        return_value=("Review analytics\n\nPosted review\nCommit: abcdef123456\nFindings: 1\nCost: not billed", True),
    )
    @patch("app.services.cursor_agent_watch.grok_store.append_message")
    @patch("app.services.cursor_agent_watch.grok_store.lookup_owned_conversation")
    @patch("app.services.cursor_agent_watch.cursor_agent_tool.fetch_run")
    def test_bugbot_watch_posts_the_review(self, fetch_run, lookup, append_message, bugbot_section):
        fetch_run.return_value = AgentRunSnapshot(
            "FINISHED",
            "Done.",
            "cursor/mail-pin",
            "https://github.com/sb11b/Storykeep-/pull/12",
            "run-1",
        )
        lookup.return_value = SimpleNamespace(id=uuid.uuid4())
        row = SimpleNamespace(
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            agent_id="bc-1",
            run_id="run-1",
            agent_url="",
            starting_branch="main",
            status="bugbot",
            created_at=datetime.now(timezone.utc),
            updated_at=None,
        )
        poll_one(MagicMock(), row)
        self.assertEqual(row.status, "posted")
        self.assertIn("Review analytics", append_message.call_args.kwargs["content"])
        self.assertIn("abcdef123456", append_message.call_args.kwargs["content"])
        bugbot_section.assert_called_once()

    @patch("app.services.cursor_agent_watch.cursor_agent_bugbot.bugbot_section", return_value=("", False))
    @patch("app.services.cursor_agent_watch.grok_store.append_message")
    @patch("app.services.cursor_agent_watch.grok_store.lookup_owned_conversation")
    @patch("app.services.cursor_agent_watch.cursor_agent_tool.fetch_run")
    def test_stale_bugbot_watch_stays_quiet(self, fetch_run, lookup, append_message, _bugbot):
        fetch_run.return_value = AgentRunSnapshot(
            "FINISHED",
            "Done.",
            "cursor/mail-pin",
            "https://github.com/sb11b/Storykeep-/pull/12",
            "run-1",
        )
        lookup.return_value = SimpleNamespace(id=uuid.uuid4())
        row = SimpleNamespace(
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            agent_id="bc-1",
            run_id="run-1",
            agent_url="",
            starting_branch="main",
            status="bugbot",
            created_at=datetime.now(timezone.utc) - timedelta(hours=4),
            updated_at=None,
        )
        poll_one(MagicMock(), row)
        self.assertEqual(row.status, "posted")
        append_message.assert_not_called()


class CursorMemoryFixTests(unittest.TestCase):
    def test_stale_prompt_section_is_replaced_and_custom_text_stays(self):
        original = (
            "# Steve\n\nCustom school note stays.\n\n"
            "## Prompt for Cursor\n\n"
            "2. **Steve supplied the task** — polish his text into one copy-paste block.\n"
        )
        updated = junior_memory.apply_cursor_memory_fix(original)
        assert updated is not None
        self.assertIn("Custom school note stays.", updated)
        self.assertNotIn("polish his text into one copy-paste block", updated)
        self.assertIn("when the run finishes", updated)
        self.assertIn("this Storykeep chat", updated)
        self.assertIsNone(junior_memory.apply_cursor_memory_fix(updated))
