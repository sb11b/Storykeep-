import unittest
from uuid import uuid4

from app.models import NoteMedia
from app.services.note_media import markdown_attachment, markdown_for_media, media_ids_in_markdown


class NoteMediaTests(unittest.TestCase):
    def test_pdf_attachment_markdown(self):
        row = NoteMedia(
            id=uuid4(),
            user_id=uuid4(),
            filename="brief.pdf",
            content_type="application/pdf",
            storage_path="/tmp/x.pdf",
            byte_size=10,
        )
        self.assertEqual(markdown_attachment(row), f"[brief.pdf](/api/v1/media/{row.id})")
        self.assertEqual(markdown_for_media(row), f"[brief.pdf](/api/v1/media/{row.id})")

    def test_media_ids_in_markdown_finds_file_links(self):
        media_id = uuid4()
        markdown = f"See [brief.pdf](/api/v1/media/{media_id}) for details."
        self.assertEqual(media_ids_in_markdown(markdown), [media_id])


if __name__ == "__main__":
    unittest.main()
