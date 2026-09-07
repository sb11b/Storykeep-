from __future__ import annotations

import unittest
from io import BytesIO

from app.services.file_extract import extract_document


class FileExtractTests(unittest.TestCase):
    def test_txt_and_rejects(self):
        title, text = extract_document("notes/Hello_World.txt", b"Line one\n\nLine two")
        self.assertEqual(title, "Hello World")
        self.assertIn("Line one", text)
        with self.assertRaises(ValueError):
            extract_document("old.doc", b"unused")
        with self.assertRaises(ValueError):
            extract_document("vault.zip", b"PK")
        with self.assertRaises(ValueError):
            extract_document("photo.png", b"\x89PNG")

    def test_pdf(self):
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        buf = BytesIO()
        writer.write(buf)
        title, text = extract_document("syllabus.pdf", buf.getvalue())
        self.assertEqual(title, "syllabus")
        self.assertIsInstance(text, str)

    def test_docx(self):
        from docx import Document

        document = Document()
        document.add_paragraph("DAT-200 homework body")
        buf = BytesIO()
        document.save(buf)
        title, text = extract_document("assignment.docx", buf.getvalue())
        self.assertEqual(title, "assignment")
        self.assertIn("DAT-200 homework body", text)


if __name__ == "__main__":
    unittest.main()
