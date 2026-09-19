from __future__ import annotations

import unittest

from app.services import junior_model


class JuniorModelTests(unittest.TestCase):
    def test_cap_slice_respects_message_and_token_caps(self):
        rows = [{"role": "user", "content": "x" * 2000} for _ in range(25)]
        capped, truncated = junior_model.cap_slice_messages(rows)
        self.assertLessEqual(len(capped), 20)
        self.assertTrue(truncated)

    def test_cap_slice_token_truncated_prefers_newest(self):
        rows = [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "y" * 40000},
            {"role": "user", "content": "newest"},
        ]
        capped, truncated = junior_model.cap_slice_messages(rows)
        self.assertTrue(truncated)
        self.assertEqual(capped[-1]["content"], "newest")

    def test_format_index_for_model_is_slim(self):
        text = junior_model.format_index_for_model(
            [
                {
                    "id": "abc",
                    "date": "2026-09-18",
                    "title": "DAT lists",
                    "summary": "Explain Python lists",
                    "note_id": "note-1",
                    "messages": 99,
                }
            ]
        )
        self.assertIn("id=abc", text)
        self.assertIn("DAT lists", text)
        self.assertIn("Explain Python lists", text)
        self.assertNotIn("note=", text)
        self.assertNotIn("99 messages", text)

    def test_filter_standing_memory_drops_spec_sections(self):
        body = "# TIMELINE\nphase 1\n# Notes\nkeep me"
        filtered = junior_model.filter_standing_memory(body, user_text="hello")
        self.assertNotIn("TIMELINE", filtered)
        self.assertIn("keep me", filtered)

    def test_filter_standing_memory_keeps_spec_when_asked(self):
        body = "# TIMELINE\nphase 1"
        kept = junior_model.filter_standing_memory(body, user_text="read TIMELINE")
        self.assertIn("TIMELINE", kept)

    def test_filter_standing_memory_always_keeps_cursor_section(self):
        body = "# TIMELINE\nphase 1\n# Prompt for Cursor\nfinish in one reply\n# Notes\nkeep me"
        filtered = junior_model.filter_standing_memory(body, user_text="hello")
        self.assertNotIn("TIMELINE", filtered)
        self.assertIn("Prompt for Cursor", filtered)
        self.assertIn("finish in one reply", filtered)
        self.assertIn("keep me", filtered)

    def test_asks_for_cursor_prompt_matches_short_requests(self):
        self.assertTrue(junior_model.asks_for_cursor_prompt("write a prompt for cursor to fix login"))
        self.assertTrue(junior_model.asks_for_cursor_prompt("give me a cursor agent prompt"))
        self.assertFalse(junior_model.asks_for_cursor_prompt("what is a database cursor"))

    def test_brings_cursor_task_when_steve_typed_the_prompt(self):
        typed = (
            "Fix the STT draft race in grok-pane.\n"
            "- Use draftValueRef on send\n"
            "- Add tests\n"
            "Done when: send includes mic transcript immediately."
        )
        self.assertTrue(junior_model.brings_cursor_task(typed))
        self.assertFalse(junior_model.asks_for_cursor_prompt(typed))

    def test_filter_does_not_dump_spec_on_cursor_ask(self):
        body = "# TIMELINE\nphase 1\n# Prompt for Cursor\nfinish in one reply"
        filtered = junior_model.filter_standing_memory(body, user_text="write a prompt for cursor to fix login")
        self.assertNotIn("TIMELINE", filtered)
        self.assertIn("Prompt for Cursor", filtered)

    def test_build_turn_extras_generate_vs_follow(self):
        generate = junior_model.build_turn_extras(
            "write a prompt for cursor to add tests",
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
        )
        self.assertIn("asked you to write", "\n".join(generate).lower())
        self.assertNotIn("SEARCH_ON", "\n".join(generate))

        typed = "Fix login in auth.py\n- add tests\n- deploy\n" + ("ensure session persists.\n" * 12)
        follow = junior_model.build_turn_extras(
            typed,
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
        )
        joined = "\n".join(follow)
        self.assertIn("supplied the cursor", joined.lower())
        self.assertNotIn("asked you to write", joined.lower())
        self.assertNotIn("SEARCH_ON", joined)

    def test_build_turn_extras_includes_railway_and_github(self):
        extras = junior_model.build_turn_extras(
            "deploy storykeep and show github commits",
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
            railway_enabled=True,
            railway_tools=True,
            github_enabled=True,
            github_tools=True,
        )
        joined = "\n".join(extras)
        self.assertIn("Railway access", joined)
        self.assertIn("GitHub access", joined)

    def test_model_payload_marks_truncated(self):
        payload = junior_model.model_payload(
            user_text="summarize",
            slice={"messages": [{"role": "user", "content": "hi"}], "truncated": True},
            standing_memory="mem",
        )
        self.assertIn("truncated=true", payload[0]["content"])


if __name__ == "__main__":
    unittest.main()
