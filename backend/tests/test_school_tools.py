from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.services.school_tools import (
    enforce_word_limit,
    extract_in_text_citations,
    format_apa_reply,
    mark_grammar_diff,
    parse_json_object,
    parse_quiz,
    run_apa,
    strip_marks,
    word_count,
)


PURPOSE_PAPER = """# DAT-200 paper

## Purpose Statement

This specific purpose wording must not be rewritten by an APA pass.

The schema stores grades (Smith, 2020).

## References

Smith 2020 databases for students
"""


class SchoolToolsTests(unittest.TestCase):
    def test_word_count_and_strip_marks(self):
        self.assertEqual(word_count("one two three"), 3)
        self.assertEqual(word_count("well ==known== method"), 3)
        self.assertEqual(strip_marks("well-==known== and <mark>clear</mark>"), "well-known and clear")

    def test_grammar_diff_marks_hyphen_fixes(self):
        original = "This is a well known method in DAT-200."
        corrected = "This is a well-known method in DAT-200."
        marked = mark_grammar_diff(original, corrected)
        self.assertIn("==well-known==", marked)
        self.assertNotIn("==This==", marked)
        self.assertEqual(strip_marks(marked), corrected)

    def test_trim_keeps_headings_and_citations_under_limit(self):
        body = " ".join(["lorem"] * 800)
        paper = f"# Heading\n\n{body}\n\n## References\n\nSmith, J. (2020). Databases."
        trimmed = enforce_word_limit(paper, 500)
        self.assertLessEqual(word_count(trimmed), 500)
        self.assertIn("# Heading", trimmed)
        self.assertIn("## References", trimmed)
        self.assertIn("Smith, J.", trimmed)

    def test_apa_reply_is_citations_block_not_purpose(self):
        reply = format_apa_reply(
            in_text=[{"from": "(Smith, 2020)", "to": "(Smith, 2020)"}],
            references="Smith, J. (2020). Databases for students. Journal of Learning, 4(2), 10–20.",
        )
        self.assertIn("# APA 7 citations", reply)
        self.assertIn("Smith, J. (2020)", reply)
        self.assertNotIn("Purpose Statement", reply)
        self.assertNotIn("This specific purpose wording", reply)
        self.assertIn("(Smith, 2020)", PURPOSE_PAPER)
        self.assertIn("Purpose Statement", PURPOSE_PAPER)

    def test_extract_in_text_does_not_need_the_body_rewritten(self):
        found = extract_in_text_citations(PURPOSE_PAPER)
        self.assertEqual(found, ["(Smith, 2020)"])

    def test_apa_rejects_body_rewrite(self):
        with patch(
            "app.services.school_tools.complete_once",
            return_value='{"in_text":[],"references":"## Purpose Statement\\n\\nrewritten"}',
        ):
            with self.assertRaises(HTTPException) as caught:
                run_apa(PURPOSE_PAPER)
        self.assertEqual(caught.exception.status_code, 502)

    def test_quiz_parse_requires_five(self):
        payload = parse_json_object(
            '{"questions":['
            '{"q":"Q1","a":"A1"},{"q":"Q2","a":"A2"},{"q":"Q3","a":"A3"},'
            '{"q":"Q4","a":"A4"},{"q":"Q5","a":"A5"}]}'
        )
        questions, md, key = parse_quiz(payload)
        self.assertEqual(len(questions), 5)
        self.assertIn("1. Q1", md)
        self.assertNotIn("A1", md)
        self.assertIn("1. A1", key)
        with self.assertRaises(HTTPException):
            parse_quiz({"questions": [{"q": "only one", "a": "x"}]})
