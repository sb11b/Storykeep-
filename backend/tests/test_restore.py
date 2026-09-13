from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.database import get_db
from app.models import Archive
from app.presenters import archive_out
from app.routers.articles import list_archives, restore_article
from app.schemas import RestoreIn
from app.services.archive import restore_article_from_archive, snapshot_article


def _article(**kwargs):
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=uuid.uuid4(),
        url="https://example.com/fusion",
        title="Fusion reactor notes",
        content_html="<p>Current body.</p>",
        content_text="Current body.",
        summary="",
        archives=[],
        is_saved=True,
        saved_at=now,
        created_at=now,
        offline_view=None,
        offline_archive_id=None,
        tags=[],
        annotations=[],
        overlay_highlights=[],
        overlay_additions=[],
        corrections=[],
        feed=SimpleNamespace(title="Physics"),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class RestoreSnapshotTests(unittest.TestCase):
    def test_html_restore_saves_current_then_loads_snapshot(self):
        old_id = uuid.uuid4()
        article = _article()
        snapshot = Archive(
            id=old_id,
            article_id=article.id,
            archive_type="readability",
            content="<p>Older snapshot.</p>",
            storage_backend="db",
            checksum="abc",
            byte_size=20,
            created_at=datetime.now(timezone.utc),
        )
        article.archives = [snapshot]
        db = MagicMock()
        restore_article_from_archive(db, article, snapshot)
        self.assertEqual(article.offline_view, "html")
        self.assertEqual(article.offline_archive_id, old_id)
        self.assertIn("Older snapshot", article.content_html or "")
        self.assertNotIn("Current body", article.content_html or "")

    def test_pdf_restore_keeps_html_and_sets_offline_view(self):
        previous = settings.data_dir
        article = _article()
        with TemporaryDirectory() as tmp:
            settings.data_dir = Path(tmp)
            try:
                db = MagicMock()
                row = snapshot_article(db, article, "pdf")
                self.assertIsNotNone(row)
                assert row is not None
                original_html = article.content_html
                original_text = article.content_text
                restore_article_from_archive(db, article, row)
                self.assertIs(article.content_html, original_html)
                self.assertIs(article.content_text, original_text)
                self.assertEqual(article.offline_view, "pdf")
                self.assertEqual(article.offline_archive_id, row.id)
                self.assertTrue(Path(row.storage_path or "").read_bytes().startswith(b"%PDF"))
            finally:
                settings.data_dir = previous

    def test_pdf_restore_missing_file_raises(self):
        article = _article()
        row = Archive(
            id=uuid.uuid4(),
            article_id=article.id,
            archive_type="pdf",
            content=None,
            storage_backend="local",
            storage_path="/tmp/missing-storykeep-pdf.pdf",
            checksum="x",
            byte_size=1,
            created_at=datetime.now(timezone.utc),
        )
        with self.assertRaises(FileNotFoundError):
            restore_article_from_archive(MagicMock(), article, row)


class RestoreApiTests(unittest.TestCase):
    def test_list_sorts_by_date_desc(self):
        older = SimpleNamespace(
            id=uuid.uuid4(),
            article_id=uuid.uuid4(),
            archive_type="readability",
            storage_backend="db",
            checksum=None,
            byte_size=1,
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        newer = SimpleNamespace(
            id=uuid.uuid4(),
            article_id=older.article_id,
            archive_type="pdf",
            storage_backend="local",
            checksum=None,
            byte_size=2,
            created_at=datetime.now(timezone.utc),
        )
        article = _article(archives=[older, newer])
        db = MagicMock()
        db.scalar.return_value = article
        user = SimpleNamespace(id=uuid.uuid4())
        rows = list_archives(article.id, db=db, user=user)
        self.assertEqual([row.id for row in rows], [newer.id, older.id])
        self.assertEqual(rows[0].type, "pdf")
        self.assertEqual(rows[1].type, "html")

    def test_restore_missing_archive_is_404(self):
        article = _article(archives=[])
        db = MagicMock()
        db.scalar.return_value = article
        user = SimpleNamespace(id=uuid.uuid4())
        with self.assertRaises(HTTPException) as caught:
            restore_article(article.id, RestoreIn(archive_id=uuid.uuid4()), db=db, user=user)
        self.assertEqual(caught.exception.status_code, 404)

    def test_restore_wrong_user_is_404(self):
        db = MagicMock()
        db.scalar.return_value = None
        user = SimpleNamespace(id=uuid.uuid4())
        with self.assertRaises(HTTPException) as caught:
            restore_article(uuid.uuid4(), RestoreIn(archive_id=uuid.uuid4()), db=db, user=user)
        self.assertEqual(caught.exception.status_code, 404)

    def test_unauth_list_and_restore_are_401_json(self):
        from app.routers.articles import router as articles_router
        from app.routers.library import router as library_router

        app = FastAPI()
        app.include_router(articles_router, prefix="/api/v1")
        app.include_router(library_router, prefix="/api/v1")

        def fake_db():
            yield MagicMock()

        app.dependency_overrides[get_db] = fake_db
        client = TestClient(app)
        article_id = uuid.uuid4()
        archive_id = uuid.uuid4()
        listed = client.get(f"/api/v1/articles/{article_id}/archives")
        self.assertEqual(listed.status_code, 401)
        self.assertEqual(listed.json(), {"detail": "Not authenticated"})
        restored = client.post(
            f"/api/v1/articles/{article_id}/restore",
            json={"archive_id": str(archive_id)},
        )
        self.assertEqual(restored.status_code, 401)
        self.assertEqual(restored.json(), {"detail": "Not authenticated"})
        pdf_file = client.get(f"/api/v1/archives/{archive_id}/file")
        self.assertEqual(pdf_file.status_code, 401)
        self.assertEqual(pdf_file.json(), {"detail": "Not authenticated"})

    def test_archive_out_pdf_download_query(self):
        row = SimpleNamespace(
            id=uuid.uuid4(),
            article_id=uuid.uuid4(),
            archive_type="pdf",
            storage_backend="local",
            checksum=None,
            byte_size=12,
            created_at=datetime.now(timezone.utc),
        )
        payload = archive_out(row)
        self.assertEqual(payload.type, "pdf")
        self.assertTrue((payload.download_url or "").endswith("/file?download=1"))


if __name__ == "__main__":
    unittest.main()
