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

    def test_powershell_wsl_paste_is_not_a_merge(self):
        msg = (
            "PS C:\\Users\\steve\\Storykeep> powershellwsl-dUbuntu\n"
            "powershellwsl-dUbuntu : The term 'powershellwsl-dUbuntu' is not recognized "
            "as the name of a cmdlet. FullyQualifiedErrorId : CommandNotFoundException\n"
            "dubantu\n"
            "just want to switch from powershell to wsl\n"
        )
        reply = cursor_agent_tool.wsl_switch_reply(msg)
        assert reply is not None
        self.assertIn("wsl -d Ubuntu", reply)
        self.assertNotIn("git merge --abort", reply)
        self.assertIsNone(cursor_agent_tool.local_merge_repair(msg))
        self.assertFalse(cursor_agent_tool.wants_start(msg))

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
        self.assertIn("Sequenced #55", task)
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
        twenty_two = cursor_agent_tool.next_step_task("go ahead and start sequenced #22")
        assert twenty_two is not None
        self.assertIn("Sequenced #22", twenty_two)
        self.assertIn("junior-client-thread-memory-get-v1", twenty_two)
        twenty_three = cursor_agent_tool.next_step_task("go ahead and start sequenced #23")
        assert twenty_three is not None
        self.assertIn("Sequenced #23", twenty_three)
        self.assertIn("junior-client-project-agents-page-v1", twenty_three)
        twenty_four = cursor_agent_tool.next_step_task("go ahead and start sequenced #24")
        assert twenty_four is not None
        self.assertIn("Sequenced #24", twenty_four)
        self.assertIn("junior-client-thread-memories-page-v1", twenty_four)
        twenty_five = cursor_agent_tool.next_step_task("go ahead and start sequenced #25")
        assert twenty_five is not None
        self.assertIn("Sequenced #25", twenty_five)
        self.assertIn("junior-client-thread-agent-get-v1", twenty_five)
        twenty_six = cursor_agent_tool.next_step_task("go ahead and start sequenced #26")
        assert twenty_six is not None
        self.assertIn("Sequenced #26", twenty_six)
        self.assertIn("junior-client-thread-agents-page-v1", twenty_six)
        twenty_seven = cursor_agent_tool.next_step_task("go ahead and start sequenced #27")
        assert twenty_seven is not None
        self.assertIn("Sequenced #27", twenty_seven)
        self.assertIn("junior-client-thread-search-get-v1", twenty_seven)
        twenty_eight = cursor_agent_tool.next_step_task("go ahead and start sequenced #28")
        assert twenty_eight is not None
        self.assertIn("Sequenced #28", twenty_eight)
        self.assertIn("junior-client-thread-search-page-v1", twenty_eight)
        twenty_nine = cursor_agent_tool.next_step_task("go ahead and start sequenced #29")
        assert twenty_nine is not None
        self.assertIn("Sequenced #29", twenty_nine)
        self.assertIn("junior-client-thread-context-get-v1", twenty_nine)
        self.assertIn("junior-client-project-search-page-v1", twenty_nine)
        thirty = cursor_agent_tool.next_step_task("go ahead and start sequenced #30")
        assert thirty is not None
        self.assertIn("Sequenced #30", thirty)
        self.assertIn("junior-client-project-search-get-v1", thirty)
        thirty_one = cursor_agent_tool.next_step_task("go ahead and start sequenced #31")
        assert thirty_one is not None
        self.assertIn("Sequenced #31", thirty_one)
        self.assertIn("junior-client-project-context-get-v1", thirty_one)
        thirty_two = cursor_agent_tool.next_step_task("go ahead and start sequenced #32")
        assert thirty_two is not None
        self.assertIn("Sequenced #32", thirty_two)
        self.assertIn("junior-client-project-memory-get-v1", thirty_two)
        thirty_three = cursor_agent_tool.next_step_task("go ahead and start sequenced #33")
        assert thirty_three is not None
        self.assertIn("Sequenced #33", thirty_three)
        self.assertIn("junior-client-project-memories-page-v1", thirty_three)
        thirty_four = cursor_agent_tool.next_step_task("go ahead and start sequenced #34")
        assert thirty_four is not None
        self.assertIn("Sequenced #34", thirty_four)
        self.assertIn("junior-client-project-message-get-v1", thirty_four)
        thirty_five = cursor_agent_tool.next_step_task("go ahead and start sequenced #35")
        assert thirty_five is not None
        self.assertIn("Sequenced #35", thirty_five)
        self.assertIn("junior-client-project-messages-page-v1", thirty_five)
        thirty_six = cursor_agent_tool.next_step_task("go ahead and start sequenced #36")
        assert thirty_six is not None
        self.assertIn("Sequenced #36", thirty_six)
        self.assertIn("junior-client-project-continue-get-v1", thirty_six)
        thirty_seven = cursor_agent_tool.next_step_task("go ahead and start sequenced #37")
        assert thirty_seven is not None
        self.assertIn("Sequenced #37", thirty_seven)
        self.assertIn("junior-client-project-thread-get-v1", thirty_seven)
        thirty_eight = cursor_agent_tool.next_step_task("go ahead and start sequenced #38")
        assert thirty_eight is not None
        self.assertIn("Sequenced #38", thirty_eight)
        self.assertIn("junior-client-project-threads-page-v1", thirty_eight)
        thirty_nine = cursor_agent_tool.next_step_task("go ahead and start sequenced #39")
        assert thirty_nine is not None
        self.assertIn("Sequenced #39", thirty_nine)
        self.assertIn("junior-client-project-thread-message-get-v1", thirty_nine)
        forty = cursor_agent_tool.next_step_task("go ahead and start sequenced #40")
        assert forty is not None
        self.assertIn("Sequenced #40", forty)
        self.assertIn("junior-client-project-thread-messages-page-v1", forty)
        forty_one = cursor_agent_tool.next_step_task("go ahead and start sequenced #41")
        assert forty_one is not None
        self.assertIn("Sequenced #41", forty_one)
        self.assertIn("junior-client-project-thread-continue-get-v1", forty_one)
        forty_two = cursor_agent_tool.next_step_task("go ahead and start sequenced #42")
        assert forty_two is not None
        self.assertIn("Sequenced #42", forty_two)
        self.assertIn("junior-client-project-thread-memory-get-v1", forty_two)
        forty_three = cursor_agent_tool.next_step_task("go ahead and start sequenced #43")
        assert forty_three is not None
        self.assertIn("Sequenced #43", forty_three)
        self.assertIn("junior-client-project-thread-memories-page-v1", forty_three)
        forty_four = cursor_agent_tool.next_step_task("go ahead and start sequenced #44")
        assert forty_four is not None
        self.assertIn("Sequenced #44", forty_four)
        self.assertIn("junior-client-project-thread-agent-get-v1", forty_four)
        forty_five = cursor_agent_tool.next_step_task("go ahead and start sequenced #45")
        assert forty_five is not None
        self.assertIn("Sequenced #45", forty_five)
        self.assertIn("junior-client-project-thread-agents-page-v1", forty_five)
        forty_six = cursor_agent_tool.next_step_task("go ahead and start sequenced #46")
        assert forty_six is not None
        self.assertIn("Sequenced #46", forty_six)
        self.assertIn("junior-client-project-thread-search-hit-get-v1", forty_six)
        forty_seven = cursor_agent_tool.next_step_task("go ahead and start sequenced #47")
        assert forty_seven is not None
        self.assertIn("Sequenced #47", forty_seven)
        self.assertIn("junior-client-project-thread-search-page-v1", forty_seven)
        forty_eight = cursor_agent_tool.next_step_task("go ahead and start sequenced #48")
        assert forty_eight is not None
        self.assertIn("Sequenced #48", forty_eight)
        self.assertIn("junior-client-project-thread-context-get-v1", forty_eight)
        forty_nine = cursor_agent_tool.next_step_task("go ahead and start sequenced #49")
        assert forty_nine is not None
        self.assertIn("Sequenced #49", forty_nine)
        self.assertIn("junior-client-thread-session-get-v1", forty_nine)
        fifty = cursor_agent_tool.next_step_task("go ahead and start sequenced #50")
        assert fifty is not None
        self.assertIn("Sequenced #50", fifty)
        self.assertIn("junior-client-thread-sessions-page-v1", fifty)
        fifty_one = cursor_agent_tool.next_step_task("go ahead and start sequenced #51")
        assert fifty_one is not None
        self.assertIn("Sequenced #51", fifty_one)
        self.assertIn("junior-client-project-thread-session-get-v1", fifty_one)
        fifty_two = cursor_agent_tool.next_step_task("go ahead and start sequenced #52")
        assert fifty_two is not None
        self.assertIn("Sequenced #52", fifty_two)
        self.assertIn("junior-client-project-thread-sessions-page-v1", fifty_two)
        fifty_three = cursor_agent_tool.next_step_task("go ahead and start sequenced #53")
        assert fifty_three is not None
        self.assertIn("Sequenced #53", fifty_three)
        self.assertIn("junior-client-project-session-get-v1", fifty_three)
        fifty_four = cursor_agent_tool.next_step_task("go ahead and start sequenced #54")
        assert fifty_four is not None
        self.assertIn("Sequenced #54", fifty_four)
        self.assertIn("junior-client-project-sessions-page-v1", fifty_four)

    def test_sequence_number_five_starts(self):
        msg = "go ahead and start Sequence number five."
        self.assertTrue(cursor_agent_tool.wants_start(msg))
        self.assertEqual(cursor_agent_tool.sequence_number(msg), 5)
        self.assertEqual(cursor_agent_tool.extract_branch(msg), "main")
        task = cursor_agent_tool.sequenced_task(msg)
        assert task is not None
        self.assertIn("Sequenced #5", task)
        self.assertIn("last_failed_post", task)
        self.assertIn("Open a pull request into main so Bugbot reviews it automatically", task)
        self.assertNotIn("Do not open a pull request", task)
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
        twenty_two = cursor_agent_tool.sequenced_task("sequenced #22")
        assert twenty_two is not None
        self.assertIn("Sequenced #22", twenty_two)
        self.assertIn("junior-client-thread-memory-get-v1", twenty_two)
        twenty_three = cursor_agent_tool.sequenced_task("sequenced #23")
        assert twenty_three is not None
        self.assertIn("Sequenced #23", twenty_three)
        self.assertIn("junior-client-project-agents-page-v1", twenty_three)
        twenty_four = cursor_agent_tool.sequenced_task("sequenced #24")
        assert twenty_four is not None
        self.assertIn("Sequenced #24", twenty_four)
        self.assertIn("junior-client-thread-memories-page-v1", twenty_four)
        twenty_five = cursor_agent_tool.sequenced_task("sequenced #25")
        assert twenty_five is not None
        self.assertIn("Sequenced #25", twenty_five)
        self.assertIn("junior-client-thread-agent-get-v1", twenty_five)
        twenty_six = cursor_agent_tool.sequenced_task("sequenced #26")
        assert twenty_six is not None
        self.assertIn("Sequenced #26", twenty_six)
        self.assertIn("junior-client-thread-agents-page-v1", twenty_six)
        twenty_seven = cursor_agent_tool.sequenced_task("sequenced #27")
        assert twenty_seven is not None
        self.assertIn("Sequenced #27", twenty_seven)
        self.assertIn("junior-client-thread-search-get-v1", twenty_seven)
        twenty_eight = cursor_agent_tool.sequenced_task("sequenced #28")
        assert twenty_eight is not None
        self.assertIn("Sequenced #28", twenty_eight)
        self.assertIn("junior-client-thread-search-page-v1", twenty_eight)
        twenty_nine = cursor_agent_tool.sequenced_task("sequenced #29")
        assert twenty_nine is not None
        self.assertIn("Sequenced #29", twenty_nine)
        self.assertIn("junior-client-thread-context-get-v1", twenty_nine)
        self.assertIn("junior-client-project-search-page-v1", twenty_nine)
        thirty = cursor_agent_tool.sequenced_task("sequenced #30")
        assert thirty is not None
        self.assertIn("Sequenced #30", thirty)
        self.assertIn("junior-client-project-search-get-v1", thirty)
        thirty_one = cursor_agent_tool.sequenced_task("sequenced #31")
        assert thirty_one is not None
        self.assertIn("Sequenced #31", thirty_one)
        self.assertIn("junior-client-project-context-get-v1", thirty_one)
        thirty_two = cursor_agent_tool.sequenced_task("sequenced #32")
        assert thirty_two is not None
        self.assertIn("Sequenced #32", thirty_two)
        self.assertIn("junior-client-project-memory-get-v1", thirty_two)
        thirty_three = cursor_agent_tool.sequenced_task("sequenced #33")
        assert thirty_three is not None
        self.assertIn("Sequenced #33", thirty_three)
        self.assertIn("junior-client-project-memories-page-v1", thirty_three)
        thirty_four = cursor_agent_tool.sequenced_task("sequenced #34")
        assert thirty_four is not None
        self.assertIn("Sequenced #34", thirty_four)
        self.assertIn("junior-client-project-message-get-v1", thirty_four)
        thirty_five = cursor_agent_tool.sequenced_task("sequenced #35")
        assert thirty_five is not None
        self.assertIn("Sequenced #35", thirty_five)
        self.assertIn("junior-client-project-messages-page-v1", thirty_five)
        thirty_six = cursor_agent_tool.sequenced_task("sequenced #36")
        assert thirty_six is not None
        self.assertIn("Sequenced #36", thirty_six)
        self.assertIn("junior-client-project-continue-get-v1", thirty_six)
        thirty_seven = cursor_agent_tool.sequenced_task("sequenced #37")
        assert thirty_seven is not None
        self.assertIn("Sequenced #37", thirty_seven)
        self.assertIn("junior-client-project-thread-get-v1", thirty_seven)
        thirty_eight = cursor_agent_tool.sequenced_task("sequenced #38")
        assert thirty_eight is not None
        self.assertIn("Sequenced #38", thirty_eight)
        self.assertIn("junior-client-project-threads-page-v1", thirty_eight)
        thirty_nine = cursor_agent_tool.sequenced_task("sequenced #39")
        assert thirty_nine is not None
        self.assertIn("Sequenced #39", thirty_nine)
        self.assertIn("junior-client-project-thread-message-get-v1", thirty_nine)
        forty = cursor_agent_tool.sequenced_task("sequenced #40")
        assert forty is not None
        self.assertIn("Sequenced #40", forty)
        self.assertIn("junior-client-project-thread-messages-page-v1", forty)
        forty_one = cursor_agent_tool.sequenced_task("sequenced #41")
        assert forty_one is not None
        self.assertIn("Sequenced #41", forty_one)
        self.assertIn("junior-client-project-thread-continue-get-v1", forty_one)
        forty_two = cursor_agent_tool.sequenced_task("sequenced #42")
        assert forty_two is not None
        self.assertIn("Sequenced #42", forty_two)
        self.assertIn("junior-client-project-thread-memory-get-v1", forty_two)
        forty_three = cursor_agent_tool.sequenced_task("sequenced #43")
        assert forty_three is not None
        self.assertIn("Sequenced #43", forty_three)
        self.assertIn("junior-client-project-thread-memories-page-v1", forty_three)
        forty_four = cursor_agent_tool.sequenced_task("sequenced #44")
        assert forty_four is not None
        self.assertIn("Sequenced #44", forty_four)
        self.assertIn("junior-client-project-thread-agent-get-v1", forty_four)
        forty_five = cursor_agent_tool.sequenced_task("sequenced #45")
        assert forty_five is not None
        self.assertIn("Sequenced #45", forty_five)
        self.assertIn("junior-client-project-thread-agents-page-v1", forty_five)
        forty_six = cursor_agent_tool.sequenced_task("sequenced #46")
        assert forty_six is not None
        self.assertIn("Sequenced #46", forty_six)
        self.assertIn("junior-client-project-thread-search-hit-get-v1", forty_six)
        forty_seven = cursor_agent_tool.sequenced_task("sequenced #47")
        assert forty_seven is not None
        self.assertIn("Sequenced #47", forty_seven)
        self.assertIn("junior-client-project-thread-search-page-v1", forty_seven)
        forty_eight = cursor_agent_tool.sequenced_task("sequenced #48")
        assert forty_eight is not None
        self.assertIn("Sequenced #48", forty_eight)
        self.assertIn("junior-client-project-thread-context-get-v1", forty_eight)
        forty_nine = cursor_agent_tool.sequenced_task("sequenced #49")
        assert forty_nine is not None
        self.assertIn("Sequenced #49", forty_nine)
        self.assertIn("junior-client-thread-session-get-v1", forty_nine)
        fifty = cursor_agent_tool.sequenced_task("sequenced #50")
        assert fifty is not None
        self.assertIn("Sequenced #50", fifty)
        self.assertIn("junior-client-thread-sessions-page-v1", fifty)
        fifty_one = cursor_agent_tool.sequenced_task("sequenced #51")
        assert fifty_one is not None
        self.assertIn("Sequenced #51", fifty_one)
        self.assertIn("junior-client-project-thread-session-get-v1", fifty_one)
        fifty_two = cursor_agent_tool.sequenced_task("sequenced #52")
        assert fifty_two is not None
        self.assertIn("Sequenced #52", fifty_two)
        self.assertIn("junior-client-project-thread-sessions-page-v1", fifty_two)
        fifty_three = cursor_agent_tool.sequenced_task("sequenced #53")
        assert fifty_three is not None
        self.assertIn("Sequenced #53", fifty_three)
        self.assertIn("junior-client-project-session-get-v1", fifty_three)
        fifty_four = cursor_agent_tool.sequenced_task("sequenced #54")
        assert fifty_four is not None
        self.assertIn("Sequenced #54", fifty_four)
        self.assertIn("junior-client-project-sessions-page-v1", fifty_four)

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
        self.assertIn("this Storykeep chat", outcome.text)
        self.assertIn("Push to main (Ubuntu)", outcome.text)
        self.assertEqual(outcome.agent_id, "bc-00000000-0000-0000-0000-000000000001")
        payload = mock_client.request.call_args.kwargs["json"]
        self.assertTrue(payload["prompt"]["text"].startswith("Add deploy polling tests"))
        self.assertIn("Bugbot reviews that pull request automatically", payload["prompt"]["text"])
        self.assertIn("Security is already enabled", payload["prompt"]["text"])
        self.assertIn("PR Routing & Approval is already enabled", payload["prompt"]["text"])
        self.assertIn("Leave automatic approval off", payload["prompt"]["text"])
        self.assertIn("Rollouts stays disabled", payload["prompt"]["text"])
        self.assertIn("Before every git push, run the Security Review agent", payload["prompt"]["text"])
        self.assertIn("Do not ask Steve to enable it", payload["prompt"]["text"])
        self.assertIn("senior-reviewer subagent", payload["prompt"]["text"])
        self.assertTrue(payload.get("autoCreatePR"))
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
        sent = mock_client.request.call_args.kwargs["json"]["prompt"]["text"]
        self.assertIn("Bugbot reviews that pull request automatically", sent)

    def test_bugbot_review_text_lists_commit_cost_and_findings(self) -> None:
        text = cursor_agent_tool.format_bugbot_reviews(
            [
                {
                    "commit_sha": "9f3c2a1b7d8e4f5061728394a5b6c7d8e9f0a1b2",
                    "pr_number": 42,
                    "bugs_found": 2,
                    "cost_cents": 42.5,
                    "dry_run": False,
                    "publication_status": "posted",
                    "bugs": [
                        {"comment_id": "2147483999", "resolution_status": "resolved", "severity": "high"},
                        {"comment_id": "2147484000", "resolution_status": "unresolved", "severity": "medium"},
                    ],
                }
            ]
        )
        self.assertIn("Review analytics", text)
        self.assertIn("Commit: 9f3c2a1b7d8e", text)
        self.assertIn("Findings: 2", text)
        self.assertIn("Cost: 42.5 cents", text)
        self.assertIn("high — resolved — comment 2147483999", text)
        self.assertIn("medium — unresolved — comment 2147484000", text)

    def test_dry_run_review_lists_title_and_location(self) -> None:
        text = cursor_agent_tool.format_bugbot_reviews(
            [
                {
                    "commit_sha": "abcdef123456",
                    "bugs_found": 1,
                    "cost_cents": None,
                    "dry_run": True,
                    "bugs": [
                        {
                            "comment_id": None,
                            "resolution_status": None,
                            "severity": "medium",
                            "title": "Unbounded retry loop",
                            "description": "retry() recurses without a ceiling.",
                            "locations": [{"file": "src/net.ts", "start_line": 5, "end_line": 9}],
                        }
                    ],
                }
            ]
        )
        self.assertIn("Dry run", text)
        self.assertIn("Cost: not billed", text)
        self.assertIn("Unbounded retry loop", text)
        self.assertIn("src/net.ts:5-9", text)
        self.assertNotIn("comment None", text)

    @patch("app.services.cursor_agent_tool._analytics_get")
    def test_bugbot_section_reads_the_pull_request(self, analytics: MagicMock) -> None:
        analytics.return_value = (
            200,
            {
                "data": [
                    {
                        "commit_sha": "abc123def456",
                        "pr_number": 12,
                        "bugs_found": 1,
                        "cost_cents": 100,
                        "dry_run": False,
                        "bugs": [{"comment_id": "9", "resolution_status": "resolved", "severity": "low"}],
                    }
                ]
            },
        )
        text, done = cursor_agent_tool.bugbot_section("https://github.com/sb11b/Storykeep-/pull/12")
        self.assertTrue(done)
        self.assertIn("Commit: abc123def456", text)
        self.assertIn("Cost: $1.00", text)
        params = analytics.call_args.args[1]
        self.assertEqual(params["repo"], "github.com/sb11b/Storykeep-")
        self.assertEqual(params["prNumber"], "12")

    @patch("app.services.github_tool.bugbot_pull_review", return_value=None)
    @patch("app.services.cursor_agent_tool._analytics_get", return_value=(401, {"message": "Invalid Team API Key"}))
    def test_team_key_rejection_waits_for_the_pull_request_review(self, analytics: MagicMock, github_review: MagicMock) -> None:
        text, done = cursor_agent_tool.bugbot_section("https://github.com/sb11b/Storykeep-/pull/3")
        self.assertFalse(done)
        self.assertEqual(text, "")
        self.assertNotIn("CURSOR_ANALYTICS_KEY", text)
        analytics.assert_called_once()
        github_review.assert_called_once_with(3)

    @patch(
        "app.services.github_tool.bugbot_pull_review",
        return_value={
            "commit_sha": "7487cb1e2c58",
            "pr_number": 10,
            "bugs_found": 1,
            "show_cost": False,
            "dry_run": False,
            "bugs": [
                {
                    "comment_id": "4139186158",
                    "resolution_status": "unresolved",
                    "severity": "low",
                    "title": "Project slug memories breaks update replay",
                    "description": "A project slug of memories can replay as a memory write.",
                    "locations": [{"file": "backend/app/services/junior_shared_clients.py", "start_line": 131, "end_line": 131}],
                }
            ],
        },
    )
    @patch("app.services.cursor_agent_tool._analytics_get", return_value=(401, {"message": "Invalid Team API Key"}))
    def test_team_key_rejection_uses_the_posted_review(self, analytics: MagicMock, github_review: MagicMock) -> None:
        text, done = cursor_agent_tool.bugbot_section("https://github.com/sb11b/Storykeep-/pull/10")
        self.assertTrue(done)
        self.assertIn("Commit: 7487cb1e2c58", text)
        self.assertIn("Findings: 1", text)
        self.assertIn("low — unresolved — comment 4139186158", text)
        self.assertIn("Project slug memories breaks update replay", text)
        self.assertIn("backend/app/services/junior_shared_clients.py:131", text)
        self.assertNotIn("Cost:", text)
        self.assertNotIn("CURSOR_ANALYTICS_KEY", text)
        github_review.assert_called_once()
        analytics.assert_called_once()

    @patch("app.services.cursor_agent_tool.settings")
    def test_start_agent_not_configured(self, mock_settings: MagicMock) -> None:
        mock_settings.cursor_api_key = ""
        outcome = cursor_agent_tool.start_agent("Do something")
        self.assertFalse(outcome.ok)
        self.assertIn("CURSOR_API_KEY", outcome.text)


if __name__ == "__main__":
    unittest.main()
