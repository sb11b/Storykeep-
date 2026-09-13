from __future__ import annotations

import unittest
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from app.services.chat import (
    MERGED_MESSAGE_CHAR_CAP,
    build_xai_messages,
    messages_for_xai,
    validate_payload,
)
from app.services.chat_attachments import (
    ATTACHMENT_CHAR_CAP,
    merge_attachment_text,
    model_supports_vision,
    vision_data_url,
)
from app.services.file_extract import extract_document
from app.services.grok_conversations import title_from_user_line


class ChatAttachmentTests(unittest.TestCase):
    def test_pdf_extract_stops_after_eight_pages(self):
        from pypdf import PdfWriter

        writer = PdfWriter()
        for _ in range(12):
            writer.add_blank_page(width=200, height=200)
        buf = BytesIO()
        writer.write(buf)
        _title, text = extract_document("pack.pdf", buf.getvalue(), max_pdf_pages=8)
        self.assertIsInstance(text, str)

    def test_title_uses_filename_when_the_message_is_empty(self):
        self.assertEqual(title_from_user_line("", ["syllabus.pdf"]), "syllabus.pdf")
        self.assertEqual(title_from_user_line("Summarize this", ["syllabus.pdf"]), "Summarize this")

    def test_vision_models(self):
        self.assertTrue(model_supports_vision("grok-4.6"))
        self.assertTrue(model_supports_vision("grok-4-fast-non-reasoning"))
        self.assertTrue(model_supports_vision("grok-2-vision-1212"))
        self.assertFalse(model_supports_vision("grok-3"))
        self.assertFalse(model_supports_vision(""))

    def test_merge_includes_extract_on_the_latest_turn_only(self):
        files = [{"filename": "notes.txt", "kind": "file", "extract_text": "Chapter one is gravity."}]
        full = merge_attachment_text("Summarize this", files, include_extracts=True)
        self.assertIn("Chapter one is gravity.", full)
        named = merge_attachment_text("Summarize this", files, include_extracts=False)
        self.assertIn("notes.txt", named)
        self.assertNotIn("gravity", named)

    def test_merge_caps_extracted_text(self):
        files = [{"filename": "big.txt", "kind": "file", "extract_text": "word " * 8000}]
        merged = merge_attachment_text("Hi", files, include_extracts=True)
        extract = merged.split("Attached file big.txt:\n", 1)[1]
        self.assertLessEqual(len(extract), ATTACHMENT_CHAR_CAP + 8)

    def test_image_without_vision_is_a_filename(self):
        files = [{"filename": "plot.png", "kind": "image", "extract_text": ""}]
        text = merge_attachment_text("", files, include_extracts=True)
        self.assertEqual(text, "Attached image: plot.png")

    def test_messages_for_xai_keeps_extract_on_the_last_user_turn(self):
        history = [
            {
                "role": "user",
                "content": "earlier",
                "files": [{"filename": "old.pdf", "kind": "file", "extract_text": "secret pages"}],
            },
            {"role": "assistant", "content": "ok"},
            {
                "role": "user",
                "content": "summarize this",
                "files": [{"filename": "lab.txt", "kind": "file", "extract_text": "The slope is 2."}],
            },
        ]
        prepared = messages_for_xai(history, model="grok-3")
        self.assertNotIn("secret pages", prepared[0]["content"])
        self.assertIn("old.pdf", prepared[0]["content"])
        self.assertIn("The slope is 2.", prepared[-1]["content"])
        cleaned = validate_payload(prepared)
        self.assertEqual(cleaned[-1]["role"], "user")
        self.assertLessEqual(len(cleaned[-1]["content"]), MERGED_MESSAGE_CHAR_CAP)

    def test_build_xai_messages_mentions_attachments(self):
        history = [{"role": "user", "content": "summarize this\n\nAttached file lab.txt:\nHello"}]
        messages = build_xai_messages(history, None, include_article=False, has_attachments=True)
        self.assertIn("attached files", messages[0]["content"].lower())

    def test_vision_data_url_compresses_a_large_png(self):
        from PIL import Image

        image = Image.new("RGB", (1800, 1200))
        pixels = image.load()
        for y in range(0, 1200, 3):
            for x in range(0, 1800, 3):
                pixels[x, y] = ((x * 13) % 256, (y * 7) % 256, (x + y) % 256)
        buf = BytesIO()
        image.save(buf, format="PNG")
        payload = buf.getvalue()
        url = vision_data_url(payload, "image/png")
        self.assertIsNotNone(url)
        self.assertTrue(url.startswith("data:image/jpeg;base64,"))
        self.assertLess(len(url), 1_800_000)

    def test_tiny_image_keeps_its_original_bytes(self):
        url = vision_data_url(b"\x89PNG\r\n\x1a\n" + b"x" * 80, "image/png")
        self.assertTrue(url.startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main()
