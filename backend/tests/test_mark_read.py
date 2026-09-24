from __future__ import annotations

import unittest

from app.services import mail_tool


class MarkReadTests(unittest.TestCase):
    def test_phrases(self):
        self.assertTrue(mail_tool.wants_mark_read("mark all unread read"))
        self.assertTrue(mail_tool.wants_mark_read("mark the email from Ada read"))
        self.assertFalse(mail_tool.wants_mark_read("mark this note read"))
        self.assertTrue(mail_tool.wants_mark_read("mark the first 10 unread"))
        self.assertFalse(mail_tool.wants_mark_read("what's on today"))

    def test_first_ten_unread(self):
        items = [{"id": str(i), "from": "Ada", "subject": f"Note {i}"} for i in range(12)]
        chosen, label = mail_tool.choose_mark_read("mark the first 10 unread", items)
        self.assertEqual(label, "all")
        self.assertEqual(len(chosen), 10)
        self.assertEqual(chosen[0]["id"], "0")
        self.assertEqual(chosen[-1]["id"], "9")

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
