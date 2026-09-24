from __future__ import annotations

import unittest

from app.services import chat, junior_model
from app.services.chat import MODEL_AUTO


class CursorPromptTurnTests(unittest.TestCase):
    def test_voice_generate_phrasing(self):
        for msg in (
            "write a prompt for cursor to fix login",
            "give me a cursor agent prompt",
            "need a prompt for the cursor to add dark mode",
            "prompt for cursor to fix the STT draft race",
        ):
            self.assertEqual(junior_model.cursor_turn_mode(msg), "generate", msg)

    def test_voice_supplied_task_without_ask(self):
        dictated = (
            "Fix the STT draft race in grok-pane use draft value ref on send add tests "
            "done when send includes mic transcript immediately"
        )
        self.assertEqual(junior_model.cursor_turn_mode(dictated), "follow")
        self.assertFalse(junior_model.asks_for_cursor_prompt(dictated))

    def test_typed_bullets_still_follow(self):
        typed = (
            "Fix the STT draft race in grok-pane.\n"
            "- Use draftValueRef on send\n"
            "- Add tests\n"
            "Done when: send includes mic transcript immediately."
        )
        self.assertEqual(junior_model.cursor_turn_mode(typed), "follow")

    def test_generate_with_embedded_details_gets_details_append(self):
        msg = "write a prompt for cursor: fix login in auth.py and add JWT refresh tests"
        extras = junior_model.build_turn_extras(
            msg,
            memory_block=None,
            chats_enabled=True,
            index_block=None,
            read_meta=None,
            unread_catalog=None,
            calendar_connected=True,
            calendar_tools=True,
            mail_connected=False,
            mail_unread=False,
            unread_mail_md=None,
            search_enabled=True,
            will_search=False,
        )
        joined = "\n".join(extras)
        self.assertIn("asked you to write", joined.lower())
        self.assertIn("already gave task details", joined.lower())
        self.assertNotIn("web_search", joined.lower())

    def test_normal_coding_question_not_cursor_task(self):
        msg = "explain python lists and how append works for my homework"
        self.assertIsNone(junior_model.cursor_turn_mode(msg))
        self.assertFalse(junior_model.is_cursor_task_turn(msg))

    def test_database_cursor_not_generate(self):
        self.assertFalse(junior_model.asks_for_cursor_prompt("what is a database cursor in SQL"))

    def test_cursor_tasks_use_xhigh_even_when_short(self):
        msg = "write a prompt for cursor to fix login"
        self.assertEqual(chat.resolve_reasoning_for_request(MODEL_AUTO, "auto", msg, []), "xhigh")

    def test_follow_task_suppresses_tools(self):
        msg = "Fix login in auth.py\n- add tests\n- deploy\n" + ("ensure session persists.\n" * 12)
        self.assertFalse(chat.should_attach_chat_tools(msg))

    def test_follow_task_starts_agent_when_configured(self):
        msg = (
            "Fix the mail list contrast in mail-overlay.tsx.\n"
            "- Unread rows stay readable on cream\n"
            "- Pin chats, notes, and folders\n"
            "Done when: refresh keeps pin order."
        )
        self.assertEqual(junior_model.cursor_turn_mode(msg), "follow")
        self.assertTrue(junior_model.should_server_start_agent(msg, configured=True))
        self.assertFalse(junior_model.should_server_start_agent(msg, configured=False))
        extras = junior_model.build_turn_extras(
            msg,
            memory_block=None,
            chats_enabled=False,
            index_block=None,
            read_meta=None,
            unread_catalog=None,
            calendar_connected=False,
            calendar_tools=False,
            mail_connected=False,
            mail_unread=False,
            unread_mail_md=None,
            search_enabled=False,
            will_search=False,
        )
        joined = "\n".join(extras)
        self.assertNotIn("cannot start", joined.lower())
        self.assertIn("agent url", joined.lower())

    def test_generate_prompt_does_not_start_agent(self):
        msg = "give me a cursor prompt to fix the mail list contrast"
        self.assertEqual(junior_model.cursor_turn_mode(msg), "generate")
        self.assertFalse(junior_model.should_server_start_agent(msg, configured=True))
        self.assertFalse(junior_model.should_server_start_agent(msg, configured=False))

    def test_explicit_start_still_starts_without_key_flag(self):
        msg = "start a cursor agent to fix the mail list"
        self.assertTrue(junior_model.should_server_start_agent(msg, configured=False))
        self.assertTrue(junior_model.should_server_start_agent(msg, configured=True))


if __name__ == "__main__":
    unittest.main()
