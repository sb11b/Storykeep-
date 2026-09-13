from __future__ import annotations

import unittest
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from pypdf import PdfReader

from app.config import settings
from app.services.archive import pdf_snapshot_path, render_article_pdf, snapshot_article


class PdfSnapshotTests(unittest.TestCase):
    def test_render_article_pdf_is_a_readable_pdf(self):
        payload = render_article_pdf("Fusion reactor notes", "The tokamak stayed online overnight.")
        self.assertTrue(payload.startswith(b"%PDF"))
        reader = PdfReader(__import__("io").BytesIO(payload))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        self.assertIn("Fusion reactor notes", text)
        self.assertIn("tokamak", text)

    def test_pdf_snapshot_path_uses_archive_id_on_data_dir(self):
        article_id = uuid.uuid4()
        archive_id = uuid.uuid4()
        previous = settings.data_dir
        with TemporaryDirectory() as tmp:
            settings.data_dir = Path(tmp)
            try:
                path = pdf_snapshot_path(article_id, archive_id)
                self.assertEqual(path, Path(tmp) / "archives" / str(article_id) / f"{archive_id}.pdf")
            finally:
                settings.data_dir = previous

    def test_snapshot_article_pdf_writes_matching_postgres_id(self):
        previous = settings.data_dir
        article = SimpleNamespace(
            id=uuid.uuid4(),
            url="https://example.com/fusion",
            title="Fusion reactor notes",
            content_html="<p>The tokamak stayed online overnight.</p>",
            content_text="The tokamak stayed online overnight.",
            summary="",
            archives=[],
            is_saved=True,
            saved_at=None,
        )
        db = MagicMock()
        with TemporaryDirectory() as tmp:
            settings.data_dir = Path(tmp)
            try:
                with (
                    patch("app.services.archive.object_store_ready", return_value=False),
                    patch("app.services.archive.upload_object_file") as upload,
                ):
                    row = snapshot_article(db, article, "pdf")
                upload.assert_not_called()
                self.assertIsNotNone(row)
                assert row is not None
                self.assertEqual(row.archive_type, "pdf")
                self.assertEqual(row.storage_backend, "local")
                path = Path(row.storage_path or "")
                self.assertTrue(path.is_file())
                self.assertEqual(path.name, f"{row.id}.pdf")
                self.assertTrue(path.read_bytes().startswith(b"%PDF"))
                self.assertEqual(path.parent, Path(tmp) / "archives" / str(article.id))
            finally:
                settings.data_dir = previous

    def test_snapshot_article_pdf_uploads_without_using_dump_key(self):
        previous = settings.data_dir
        article = SimpleNamespace(
            id=uuid.uuid4(),
            url="https://example.com/fusion",
            title="Notes",
            content_html="<p>Body.</p>",
            content_text="Body.",
            summary="",
            archives=[],
            is_saved=True,
            saved_at=None,
        )
        db = MagicMock()
        with TemporaryDirectory() as tmp:
            settings.data_dir = Path(tmp)
            try:
                with (
                    patch("app.services.archive.object_store_ready", return_value=True),
                    patch("app.services.archive.settings.s3_prefix", "storykeep"),
                    patch("app.services.archive.upload_object_file") as upload,
                ):
                    row = snapshot_article(db, article, "pdf")
                self.assertIsNotNone(row)
                assert row is not None
                self.assertEqual(row.storage_backend, "s3")
                upload.assert_called_once()
                key = upload.call_args.args[1]
                self.assertEqual(key, f"storykeep/pdf-snapshots/{row.id}.pdf")
                self.assertFalse(key.startswith("storykeep/storykeep-db-"))
            finally:
                settings.data_dir = previous

    def test_html_snapshot_still_stores_readability_in_db(self):
        article = SimpleNamespace(
            id=uuid.uuid4(),
            url="https://example.com/fusion",
            title="Notes",
            content_html="<p>Hello</p>",
            content_text="Hello",
            summary="",
            archives=[],
            is_saved=True,
            saved_at=None,
        )
        db = MagicMock()
        row = snapshot_article(db, article, "html")
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.archive_type, "readability")
        self.assertEqual(row.storage_backend, "db")
        self.assertIn("Hello", row.content or "")


if __name__ == "__main__":
    unittest.main()
