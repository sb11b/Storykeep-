from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import cursor_agent_tool, junior_model, railway_tool
from app.services.cursor_agent_intent import wants_start


class OpsTurnTests(unittest.TestCase):
    def test_is_ops_turn_for_github_then_deploy(self):
        msg = "Show GitHub status, then deploy Storykeep."
        self.assertTrue(junior_model.is_ops_turn(msg))
        self.assertTrue(railway_tool.wants_railway_deploy(msg))

    def test_build_turn_extras_ops_includes_ops_append(self):
        extras = junior_model.build_turn_extras(
            "Show GitHub status, then deploy Storykeep.",
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
            search_enabled=True,
            will_search=False,
            railway_enabled=True,
            railway_tools=True,
            github_enabled=True,
            github_tools=True,
            ops_turn=True,
        )
        joined = "\n".join(extras)
        self.assertIn("Owner ops twin turn", joined)
        self.assertIn("Storykeep web", joined)

    def test_is_ops_turn_false_for_cline_pending(self):
        self.assertFalse(junior_model.is_ops_turn("Cline pending"))
        self.assertFalse(junior_model.is_ops_turn("The Cline operator is pending"))

    def test_is_ops_turn_false_for_approve_or_deny(self):
        self.assertFalse(junior_model.is_ops_turn("Approve or Deny"))
        self.assertFalse(junior_model.is_ops_turn("Please Approve or Deny this request"))

    def test_is_ops_turn_false_for_git_add(self):
        self.assertFalse(junior_model.is_ops_turn("git add backend/app/main.py"))
        self.assertFalse(junior_model.is_ops_turn("git add ."))
        self.assertFalse(junior_model.is_ops_turn("git status"))

    def test_is_ops_turn_true_for_github_status(self):
        self.assertTrue(junior_model.is_ops_turn("Show GitHub status"))
        self.assertTrue(junior_model.is_ops_turn("What is on github?"))

    def test_is_delegate_turn_false_for_cline_pending(self):
        with patch("app.services.cursor_agent_tool.settings") as mock_settings:
            mock_settings.cursor_api_key = "test_key"
            self.assertFalse(junior_model.is_delegate_turn("Cline pending"))
            self.assertFalse(junior_model.is_delegate_turn("Approve or Deny"))

    def test_is_prompt_only_turn_matches_write_cline_prompt_do_not_start(self):
        self.assertTrue(junior_model.is_prompt_only_turn("Write a Cline prompt only. Do not start Cursor."))
        self.assertTrue(junior_model.is_prompt_only_turn("write a cline prompt. do not start cursor."))
        self.assertFalse(junior_model.is_prompt_only_turn("Write a Cline prompt to fix the login bug"))
        self.assertFalse(junior_model.is_prompt_only_turn("Start a cursor agent to fix the login bug"))

    def test_build_turn_extras_prompt_only_appends_prompt_only(self):
        extras = junior_model.build_turn_extras(
            "Write a Cline prompt only. Do not start Cursor.",
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
            prompt_only_turn=True,
        )
        joined = "\n".join(extras)
        self.assertIn("Steve asked you to write a Cline prompt", joined)
        self.assertNotIn("copy-paste block", joined)

    def test_build_turn_extras_normal_cursor_prompt_appends_cursor_prompt(self):
        extras = junior_model.build_turn_extras(
            "Write a Cline prompt to fix the login bug",
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
            prompt_only_turn=False,
        )
        joined = "\n".join(extras)
        self.assertIn("copy-paste block", joined)
        self.assertNotIn("Reply with ONLY one fenced code block", joined)

    def test_is_cline_operator_message_detects_patterns(self):
        self.assertTrue(junior_model.is_cline_operator_message("Cline pending"))
        self.assertTrue(junior_model.is_cline_operator_message("The Cline operator is pending"))
        self.assertTrue(junior_model.is_cline_operator_message("Approve or Deny"))
        self.assertFalse(junior_model.is_cline_operator_message("Start a cursor agent"))
        self.assertFalse(junior_model.is_cline_operator_message("Show GitHub status"))


    def test_pick_xhigh_for_auto_false_when_asks_for_cursor_prompt(self):
        from app.services import chat as chat_service
        msg = "Write me a Cursor prompt to fix the login bug on Railway."
        self.assertTrue(junior_model.asks_for_cursor_prompt(msg))
        self.assertFalse(chat_service.pick_xhigh_for_auto(msg))
        self.assertEqual(chat_service.resolve_reasoning_for_request(chat_service.MODEL_AUTO, "auto", msg, []), "low")

    def test_pick_xhigh_for_auto_false_when_do_not_start_cursor(self):
        from app.services import chat as chat_service
        msg = "Do not start Cursor Agent. Just give me a prompt for the Railway deploy."
        self.assertFalse(chat_service.pick_xhigh_for_auto(msg))
        self.assertEqual(chat_service.resolve_reasoning_for_request(chat_service.MODEL_AUTO, "auto", msg, []), "low")

    def test_pick_xhigh_for_auto_false_sequence_number(self):
        from app.services import chat as chat_service
        msg = "sequenced #68 pick xhigh"
        self.assertFalse(chat_service.pick_xhigh_for_auto(msg))
        self.assertEqual(chat_service.resolve_reasoning_for_request(chat_service.MODEL_AUTO, "auto", msg, []), "low")

    def test_pick_xhigh_for_auto_false_write_cline_prompt(self):
        from app.services import chat as chat_service
        msg = "write a Cline prompt to fix the bug"
        self.assertFalse(chat_service.pick_xhigh_for_auto(msg))
        self.assertEqual(chat_service.resolve_reasoning_for_request(chat_service.MODEL_AUTO, "auto", msg, []), "low")

    def test_pick_xhigh_for_auto_false_file_path(self):
        from app.services import chat as chat_service
        msg = "backend/app/services/chat.py needs review"
        self.assertFalse(chat_service.pick_xhigh_for_auto(msg))
        self.assertEqual(chat_service.resolve_reasoning_for_request(chat_service.MODEL_AUTO, "auto", msg, []), "low")

    def test_pick_xhigh_for_auto_false_cline_result(self):
        from app.services import chat as chat_service
        msg = "Cline returned the fix for login"
        self.assertFalse(chat_service.pick_xhigh_for_auto(msg))
        self.assertEqual(chat_service.resolve_reasoning_for_request(chat_service.MODEL_AUTO, "auto", msg, []), "low")

    def test_pick_xhigh_for_auto_false_sequence_with_explicit(self):
        from app.services import chat as chat_service
        # Sequence numbers no longer trigger xhigh, even with explicit start words.
        msg = "go ahead and start sequenced #68"
        self.assertFalse(chat_service.pick_xhigh_for_auto(msg))
        self.assertEqual(chat_service.resolve_reasoning_for_request(chat_service.MODEL_AUTO, "auto", msg, []), "low")

    def test_wants_start_false_for_sequence_number(self):
        msg = "sequenced #68 pick xhigh"
        self.assertFalse(wants_start(msg))

    def test_wants_start_false_for_write_cline_prompt(self):
        msg = "write a Cline prompt to fix the bug"
        self.assertFalse(wants_start(msg))

    def test_wants_start_false_for_file_path(self):
        msg = "backend/app/services/chat.py needs review"
        self.assertFalse(wants_start(msg))

    def test_wants_start_false_for_cline_result(self):
        msg = "Cline returned the fix for login"
        self.assertFalse(wants_start(msg))

    def test_wants_start_false_sequence_with_explicit(self):
        # Sequence numbers return False early, even with explicit start words.
        msg = "go ahead and start sequenced #68"
        self.assertFalse(wants_start(msg))

    def test_pasted_git_status_stays_low(self):
        from app.services import chat as chat_service
        msg = (
            "On branch main\n"
            "Your branch is up to date with 'origin/main'.\n\n"
            "Changes to be committed:\n"
            "  (use \"git restore --staged <file>...\" to unstage)\n"
            "        modified:   backend/app/services/chat.py\n\n"
            "Changes not staged for commit:\n"
            "  (use \"git add <file>...\" to update what will be committed)\n"
            "        modified:   backend/app/services/junior_model.py\n"
        )
        self.assertTrue(junior_model.is_pasted_ops_log(msg))
        self.assertFalse(junior_model.is_ops_turn(msg))
        self.assertFalse(chat_service.pick_xhigh_for_auto(msg))
        self.assertEqual(
            chat_service.resolve_reasoning_for_request(
                chat_service.MODEL_AUTO, "auto", msg, []
            ),
            "low",
        )

    def test_on_branch_alone_is_not_pasted_ops_log(self):
        # A sentence with only "on branch" must not be treated as a pasted log.
        self.assertFalse(junior_model.is_pasted_ops_log("Show GitHub status on branch main"))
        # And it must still be an ops turn.
        self.assertTrue(junior_model.is_ops_turn("Show GitHub status on branch main"))

    def test_sentence_with_two_phrases_is_not_pasted_ops_log(self):
        # Two git phrases in a sentence are not a pasted log.
        msg = "Check GitHub status. On branch main, nothing to commit."
        self.assertFalse(junior_model.is_pasted_ops_log(msg))
        # It must still be an ops turn.
        self.assertTrue(junior_model.is_ops_turn(msg))

    def test_is_cline_pending_command_detects_command_paste(self):
        self.assertTrue(junior_model.is_cline_pending_command("Cline pending\ngit add -A"))
        self.assertTrue(junior_model.is_cline_pending_command("Approve or Deny\ngit status"))
        self.assertTrue(junior_model.is_cline_pending_command("Cline pending\ndir /s"))
        self.assertFalse(junior_model.is_cline_pending_command("Cline pending"))
        self.assertFalse(junior_model.is_cline_pending_command("git status"))
        self.assertFalse(junior_model.is_cline_pending_command("Approve or Deny"))

    def test_cline_pending_reply_git_add_dash_a_starts_with_deny(self):
        msg = "Cline pending\ngit add -A"
        reply = junior_model.get_cline_pending_reply(msg)
        self.assertIsNotNone(reply)
        self.assertTrue(reply.startswith("Deny"))

    def test_cline_pending_reply_git_status_starts_with_approve(self):
        msg = "Cline pending\ngit status"
        reply = junior_model.get_cline_pending_reply(msg)
        self.assertIsNotNone(reply)
        self.assertTrue(reply.startswith("Approve"))

    def test_cline_pending_reply_dir_s_starts_with_deny(self):
        msg = "Cline pending\ndir /s"
        reply = junior_model.get_cline_pending_reply(msg)
        self.assertIsNotNone(reply)
        self.assertTrue(reply.startswith("Deny"))

    def test_build_turn_extras_cline_pending_includes_append(self):
        extras = junior_model.build_turn_extras(
            "Cline pending\ngit add -A",
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
        self.assertIn("Cline Pending command", joined)
        self.assertIn("Approve or Deny", joined)

    def test_pick_xhigh_for_auto_false_cline_pending_command(self):
        from app.services import chat as chat_service
        msg = "Cline pending\ngit add -A"
        self.assertFalse(chat_service.pick_xhigh_for_auto(msg))
        self.assertEqual(chat_service.resolve_reasoning_for_request(chat_service.MODEL_AUTO, "auto", msg, []), "low")

    def test_cline_pending_reply_contains_shell_metachar_deny(self):
        # Deny if command contains &&, ;, |, or newline
        self.assertTrue(junior_model.get_cline_pending_reply("Cline pending\ngit status && ls").startswith("Deny"))
        self.assertTrue(junior_model.get_cline_pending_reply("Cline pending\ngit status; ls").startswith("Deny"))
        self.assertTrue(junior_model.get_cline_pending_reply("Cline pending\ngit status | cat").startswith("Deny"))

    def test_cline_pending_git_add_named_backend_approved(self):
        # Approve git add only with named backend/ paths
        reply = junior_model.get_cline_pending_reply("Cline pending\ngit add backend/app/main.py")
        self.assertIsNotNone(reply)
        self.assertTrue(reply.startswith("Approve"))
        self.assertIn("backend/app/main.py", reply)

    def test_cline_pending_git_add_dash_a_deny(self):
        # Deny git add -A, git add ., git add --all
        self.assertTrue(junior_model.get_cline_pending_reply("Cline pending\ngit add -A").startswith("Deny"))
        self.assertTrue(junior_model.get_cline_pending_reply("Cline pending\ngit add .").startswith("Deny"))
        self.assertTrue(junior_model.get_cline_pending_reply("Cline pending\ngit add --all").startswith("Deny"))

    def test_cline_pending_git_push_head_without_cursor_branch_deny(self):
        # Deny git push github HEAD unless paste shows cursor/ branch
        msg = "Cline pending\ngit push github HEAD"
        reply = junior_model.get_cline_pending_reply(msg)
        self.assertIsNotNone(reply)
        self.assertTrue(reply.startswith("Deny"))

    def test_cline_pending_git_push_head_with_cursor_branch_approve(self):
        # Approve git push github HEAD when paste shows "On branch cursor/..."
        msg = "Cline pending\nOn branch cursor/cline-pending-reply-shape\ngit push github HEAD"
        reply = junior_model.get_cline_pending_reply(msg)
        self.assertIsNotNone(reply)
        self.assertTrue(reply.startswith("Approve"))

    def test_cline_pending_git_push_head_with_cursor_word_not_on_branch_deny(self):
        # Deny git push github HEAD when "cursor/" appears but not in "On branch cursor/..."
        msg = "Cline pending\ncursor/cline-pending-reply-shape\ngit push github HEAD"
        reply = junior_model.get_cline_pending_reply(msg)
        self.assertIsNotNone(reply)
        self.assertTrue(reply.startswith("Deny"))

    def test_cline_pending_git_push_head_with_main_branch_deny(self):
        # Deny git push github HEAD when paste shows "On branch main"
        msg = "Cline pending\nOn branch cursor/test\nOn branch main\ngit push github HEAD"
        reply = junior_model.get_cline_pending_reply(msg)
        self.assertIsNotNone(reply)
        self.assertTrue(reply.startswith("Deny"))

    def test_cline_pending_next_command_is_fenced_block(self):
        # Next command is always a fenced code block
        reply = junior_model.get_cline_pending_reply("Cline pending\ngit status")
        self.assertIn("```", reply)
        reply2 = junior_model.get_cline_pending_reply("Cline pending\ngit add -A")
        self.assertIn("```", reply2)

    def test_cline_pending_command_indented_under_header(self):
        # Match a command indented under "Cline pending:"
        msg = "Cline pending:\n    git status"
        self.assertTrue(junior_model.is_cline_pending_command(msg))
        reply = junior_model.get_cline_pending_reply(msg)
        self.assertIsNotNone(reply)
        self.assertTrue(reply.startswith("Approve"))

    def test_cline_pending_git_add_non_backend_deny(self):
        # Deny git add of non-backend paths
        reply = junior_model.get_cline_pending_reply("Cline pending\ngit add frontend/app/main.py")
        self.assertTrue(reply.startswith("Deny"))

    def test_cline_pending_git_add_multiple_backend_approved(self):
        # Approve git add with multiple backend/ paths
        reply = junior_model.get_cline_pending_reply("Cline pending\ngit add backend/app/main.py backend/tests/test.py")
        self.assertTrue(reply.startswith("Approve"))

    def test_cline_pending_git_add_wildcard_deny(self):
        # Deny git add with wildcard patterns
        reply = junior_model.get_cline_pending_reply("Cline pending\ngit add *.py")
        self.assertTrue(reply.startswith("Deny"))

    def test_cline_pending_git_add_dotdot_deny(self):
        # Deny git add with .. path traversal
        reply = junior_model.get_cline_pending_reply("Cline pending\ngit add backend/../other.py")
        self.assertTrue(reply.startswith("Deny"))

    def test_cline_pending_git_add_question_mark_deny(self):
        # Deny git add with ? glob character
        reply = junior_model.get_cline_pending_reply("Cline pending\ngit add backend/app?.py")
        self.assertTrue(reply.startswith("Deny"))

    def test_cline_pending_git_add_bracket_deny(self):
        # Deny git add with [ glob character
        reply = junior_model.get_cline_pending_reply("Cline pending\ngit add backend/app[0-9].py")
        self.assertTrue(reply.startswith("Deny"))

    def test_cline_pending_multiple_commands_deny(self):
        # Deny if paste contains more than one command-like line
        reply = junior_model.get_cline_pending_reply("Cline pending\ngit status\npip install requests")
        self.assertIsNotNone(reply)
        self.assertTrue(reply.startswith("Deny"))

    def test_cline_pending_pwsh_second_command_deny(self):
        # Deny if paste contains pwsh as a second command line
        reply = junior_model.get_cline_pending_reply(
            'Cline pending\ngit status\npwsh -Command "git push github main"'
        )
        self.assertIsNotNone(reply)
        self.assertTrue(reply.startswith("Deny"))

    def test_cline_pending_pwsh_pending_word_second_command_deny(self):
        # Deny if paste contains a second command line with the word "pending"
        reply = junior_model.get_cline_pending_reply(
            'Cline pending\ngit status\npwsh -Command "pending"'
        )
        self.assertIsNotNone(reply)
        self.assertTrue(reply.startswith("Deny"))


if __name__ == "__main__":
    unittest.main()
