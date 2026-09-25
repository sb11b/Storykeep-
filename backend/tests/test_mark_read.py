from __future__ import annotations

import unittest

from app.services import mail_tool


class MarkReadTests(unittest.TestCase):
    def test_phrases(self):
        self.assertTrue(mail_tool.wants_mark_read("mark all unread read"))
        self.assertTrue(mail_tool.wants_mark_read("mark the email from Ada read"))
        self.assertFalse(mail_tool.wants_mark_read("mark this note read"))
        self.assertTrue(mail_tool.wants_mark_read("mark the first 10 unread"))
        self.assertTrue(mail_tool.wants_mark_read("mark the first ten emails unread"))
        self.assertFalse(mail_tool.wants_mark_read("what's on today"))

    def test_first_ten_unread(self):
        items = [{"id": str(i), "from": "Ada", "subject": f"Note {i}"} for i in range(12)]
        chosen, label = mail_tool.choose_mark_read("mark the first 10 unread", items)
        self.assertEqual(label, "all")
        self.assertEqual(len(chosen), 10)
        self.assertEqual(chosen[0]["id"], "0")
        self.assertEqual(chosen[-1]["id"], "9")
        spoken, spoken_label = mail_tool.choose_mark_read("mark the first ten emails unread", items)
        self.assertEqual(spoken_label, "all")
        self.assertEqual(len(spoken), 10)
        self.assertEqual(spoken[0]["id"], "0")

    def test_all_unread(self):
        items = [{"id": "1", "from": "Ada", "subject": "Syllabus"}]
        chosen, label = mail_tool.choose_mark_read("mark all unread read", items)
        self.assertEqual(label, "all")
        self.assertEqual(chosen, items)
        text = mail_tool.format_mark_read(chosen, marked=1, label=label, connected=True)
        self.assertIn("Marked 1 unread message read.", text)
        self.assertIn("Ada — Syllabus", text)

    def test_from_match(self):
        items = [
            {"id": "1", "from": "Ada Lovelace", "subject": "Syllabus"},
            {"id": "2", "from": "Bob", "subject": "Hello"},
        ]
        chosen, label = mail_tool.choose_mark_read("mark the email from Ada read", items)
        self.assertEqual(label, "Ada")
        self.assertEqual([item["id"] for item in chosen], ["1"])

    def test_subject_match(self):
        items = [{"id": "1", "from": "Ada", "subject": "Syllabus update"}]
        chosen, label = mail_tool.choose_mark_read("mark the syllabus email read", items)
        self.assertEqual(label, "syllabus")
        self.assertEqual(len(chosen), 1)

    def test_vague_does_not_mark_the_inbox(self):
        items = [{"id": "1", "from": "Ada", "subject": "Syllabus"}]
        chosen, label = mail_tool.choose_mark_read("mark mail read", items)
        self.assertEqual(label, "vague")
        self.assertEqual(chosen, [])
        self.assertIn("mark all unread read", mail_tool.format_mark_read(chosen, marked=0, label=label, connected=True))


class SpecificMailTests(unittest.TestCase):
    def test_action_does_not_steal_mark_read(self):
        self.assertIsNone(mail_tool.mail_action("mark the email from Ada read"))
        self.assertIsNone(mail_tool.mail_action("mark the first 10 unread"))
        self.assertIsNone(mail_tool.mail_action("read this note"))
        self.assertEqual(mail_tool.mail_action("read the email from Ada"), "read")
        self.assertEqual(mail_tool.mail_action("copy the syllabus email"), "copy")
        self.assertEqual(mail_tool.mail_action("post the email from Ada in chat"), "post")
        self.assertEqual(mail_tool.mail_action("delete the email from Ada"), "delete")

    def test_many_matches_do_not_delete(self):
        items = [
            {"id": "1", "from": "Ada Lovelace", "subject": "Syllabus"},
            {"id": "2", "from": "Ada Lovelace", "subject": "Quiz"},
        ]
        chosen, label = mail_tool.choose_specific("delete the email from Ada", items)
        self.assertEqual(len(chosen), 2)
        self.assertIn("Name one", mail_tool.format_specific("delete", chosen, label, connected=True))

    def test_bulk_delete_refuses(self):
        self.assertEqual(mail_tool.choose_specific("delete all email", [{"id": "1"}])[1], "bulk")
        self.assertIn("will not delete every", mail_tool.format_specific("delete", [], "bulk", connected=True))

    def test_read_copy_post_one_message(self):
        from unittest.mock import patch

        item = {"id": "a", "from": "Ada", "subject": "Syllabus", "date": "2026-09-24T12:00:00Z", "preview": "short"}
        full = {**item, "body": "Bring a pencil."}
        with (
            patch("app.services.fastmail_jmap.list_emails", return_value={"items": [item]}) as listed,
            patch("app.services.fastmail_jmap.get_email", return_value=full) as got,
            patch("app.services.fastmail_jmap.destroy_emails") as destroyed,
        ):
            read = mail_tool.specific_mail_reply("tok", "read the email from Ada")
            copied = mail_tool.specific_mail_reply("tok", "copy the email from Ada")
            posted = mail_tool.specific_mail_reply("tok", "post the email from Ada in chat")
            deleted = mail_tool.specific_mail_reply("tok", "delete the email from Ada")
        self.assertIn("Bring a pencil.", read)
        self.assertIn("From: Ada", read)
        self.assertIn("```", copied)
        self.assertIn("Bring a pencil.", copied)
        self.assertIn("> From: Ada", posted)
        self.assertIn("Deleted 1 message.", deleted)
        self.assertEqual(got.call_count, 3)
        destroyed.assert_called_once()
        self.assertTrue(listed.called)
