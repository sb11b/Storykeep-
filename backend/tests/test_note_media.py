import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from app.models import NoteMedia
from app.services.note_media import (
    markdown_attachment,
    markdown_for_media,
    media_ids_in_markdown,
    media_storage_path,
    sniff_image_media_type,
    storykeep_download_filename,
)


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

    def test_download_filename_uses_storykeep_id_and_type(self):
        media_id = uuid4()
        self.assertEqual(
            storykeep_download_filename(media_id, "image/jpeg", "selfie.jpg"),
            f"storykeep-{media_id}.jpg",
        )
        self.assertEqual(
            storykeep_download_filename(media_id, "image/png", "pic.bin"),
            f"storykeep-{media_id}.png",
        )
        self.assertNotEqual(storykeep_download_filename(media_id, "image/jpeg"), "download")

    def test_sniff_jpeg_header(self):
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as handle:
            handle.write(b"\xff\xd8\xff\xe0" + b"\x00" * 12)
            path = Path(handle.name)
        try:
            self.assertEqual(sniff_image_media_type(path, "application/octet-stream"), "image/jpeg")
            self.assertEqual(sniff_image_media_type(path, "image/jpeg"), "image/jpeg")
        finally:
            path.unlink(missing_ok=True)

    def test_new_media_files_are_written_under_data_dir(self):
        from app.config import settings

        user_id = uuid4()
        media_id = uuid4()
        previous = settings.data_dir
        with tempfile.TemporaryDirectory() as tmp:
            settings.data_dir = Path(tmp)
            try:
                path = media_storage_path(user_id, media_id, ".jpg")
                self.assertEqual(path, Path(tmp) / "note-media" / str(user_id) / f"{media_id}.jpg")
                self.assertTrue(path.parent.is_dir())
            finally:
                settings.data_dir = previous


if __name__ == "__main__":
    unittest.main()
