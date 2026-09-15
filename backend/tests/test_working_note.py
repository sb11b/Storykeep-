from __future__ import annotations

import unittest

from app.services.chat import build_xai_messages, is_small_talk_turn, should_attach_working_note
from app.services.include_chunk import WORKING_NOTE_CHAR_CAP, resolve_include_slice
from app.database import SessionLocal
from app.models import User
from app.services.note_revisions import list_revisions
from app.services.vault_import import create_composed_note
from app.services.working_note import apply_junior_reply, extract_apply_markdown, heading_from_instruction, merge_working_note


NOTE = """# Lab notes

## Section 1

Keep this opening intact.

## Section 2

This section is too wordy and rambling and needs a tighter rewrite.

## Section 3

Closing facts stay here.
"""


class WorkingNoteTests(unittest.TestCase):
    def test_hello_does_not_attach_working_note(self):
        self.assertTrue(is_small_talk_turn("hello"))
        self.assertFalse(should_attach_working_note("hello"))
        self.assertTrue(should_attach_working_note("tighten section 2"))

    def test_working_excerpt_is_in_system_not_user_textarea(self):
        messages = build_xai_messages(
            [{"role": "user", "content": "tighten section 2"}],
            None,
            include_article=False,
            working_excerpt="working_note_id: abc\nTitle: Lab\n\n## Section 2\nwordy",
        )
        system = messages[0]["content"]
        self.assertIn("Work in Junior", system)
        self.assertIn("not in his textarea", system)
        self.assertIn("## Section 2", system)
        self.assertEqual(messages[-1]["content"], "tighten section 2")
        self.assertNotIn("general-knowledge mode", system)

    def test_heading_from_section_number(self):
        self.assertEqual(heading_from_instruction("tighten section 2", NOTE), "Section 2")

    def test_apply_heading_keeps_other_sections(self):
        reply = "```markdown\n## Section 2\n\nShort and clear.\n```"
        merged = merge_working_note(NOTE, reply, mode="heading", heading="Section 2")
        self.assertIn("Keep this opening intact", merged)
        self.assertIn("Short and clear", merged)
        self.assertIn("Closing facts stay here", merged)
        self.assertNotIn("too wordy", merged)

    def test_extract_fence(self):
        self.assertEqual(extract_apply_markdown("Sure.\n```md\n# New\n```"), "# New")

    def test_working_note_cap_offers_next_chunk(self):
        huge = "# Book\n\n" + ("chapter text " * 20_000)
        self.assertGreater(len(huge), WORKING_NOTE_CHAR_CAP)
        slice = resolve_include_slice(
            huge,
            mode="chunk",
            title="Book",
            cap=WORKING_NOTE_CHAR_CAP,
            hard_max=WORKING_NOTE_CHAR_CAP,
        )
        self.assertLessEqual(slice.chars, WORKING_NOTE_CHAR_CAP)
        self.assertTrue(slice.has_more)
        self.assertIsNotNone(slice.next_offset)


class WorkingNoteApplyTests(unittest.TestCase):
    def setUp(self) -> None:
        import uuid

        self.db = SessionLocal()
        self.user = User(
            id=uuid.uuid4(),
            email=f"work-junior-{uuid.uuid4()}@example.com",
            password_hash="x",
        )
        self.db.add(self.user)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.rollback()
        self.db.close()

    def test_apply_creates_revision_and_undo_restores(self):
        article = create_composed_note(self.db, self.user, "Lab notes", NOTE, destination="notes")
        apply_junior_reply(
            self.db,
            self.user,
            article,
            "## Section 2\n\nShort and clear.",
            mode="heading",
            heading="Section 2",
        )
        self.assertIn("Short and clear", article.content_text or "")
        self.assertIn("Keep this opening intact", article.content_text or "")
        rows = list_revisions(self.db, self.user, article)
        self.assertEqual(len(rows), 1)
        self.assertIn("too wordy", rows[0].markdown)
        from app.services.vault_import import update_composed_note

        update_composed_note(
            self.db,
            self.user,
            article,
            "Lab notes",
            rows[0].markdown,
            confirm_short=True,
            snapshot=False,
        )
        self.assertIn("too wordy", article.content_text or "")


if __name__ == "__main__":
    unittest.main()
