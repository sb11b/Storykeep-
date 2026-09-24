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
        self.assertIn("git merge github/cursor/mail-pin", text)
        self.assertIn("What changed: Fixed the mail list contrast", text)
        self.assertIn("pull/12", text)
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

    @patch("app.services.cursor_agent_watch.grok_store.append_message")
    @patch("app.services.cursor_agent_watch.grok_store.lookup_owned_conversation")
    @patch("app.services.cursor_agent_watch.cursor_agent_tool.fetch_run")
    def test_poll_posts_once(self, fetch_run, lookup, append_message):
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
        self.assertIn("git merge github/cursor/mail-pin", content)

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
        self.assertIsNone(junior_memory.apply_cursor_memory_fix(updated))
