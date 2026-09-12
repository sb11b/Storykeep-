from __future__ import annotations

import json
import unittest
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.backup import _build_export_payload, _dated_backup_name, _write_export_bundle


class BackupExportTests(unittest.TestCase):
    def test_dated_backup_name(self):
        backup_id = uuid.UUID("11111111-2222-3333-4444-555555555555")
        when = datetime(2026, 9, 12, 4, 39, tzinfo=timezone.utc)
        self.assertEqual(_dated_backup_name("export", backup_id, when, ".zip"), "storykeep-export-2026-09-12-11111111.zip")

    def test_write_export_bundle_contains_json_and_media(self):
        media_id = uuid.uuid4()
        with TemporaryDirectory() as tmp:
            media_path = Path(tmp) / "sample.png"
            media_path.write_bytes(b"\x89PNG\r\n\x1a\n")
            payload = {"format": "storykeep-archive", "media": [{"id": str(media_id), "archive_path": f"media/{media_id}.png"}]}
            row = SimpleNamespace(id=media_id, storage_path=str(media_path), filename="sample.png")
            bundle = Path(tmp) / "storykeep-export-2026-09-12-test.zip"
            _write_export_bundle(bundle, payload, [row])
            with zipfile.ZipFile(bundle) as zf:
                names = zf.namelist()
                self.assertIn("archive.json", names)
                self.assertIn(f"media/{media_id}.png", names)
                loaded = json.loads(zf.read("archive.json"))
                self.assertEqual(loaded["format"], "storykeep-archive")

    def test_build_export_payload_includes_folders_and_media_manifest(self):
        user = SimpleNamespace(id=uuid.uuid4(), email="test@example.com", display_name="Test")
        folder = SimpleNamespace(
            id=uuid.uuid4(),
            shelf="schoolwork",
            name="DAT-325",
            created_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
        )
        media = SimpleNamespace(
            id=uuid.uuid4(),
            filename="diagram.png",
            content_type="image/png",
            byte_size=12,
            created_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
            storage_path="/tmp/diagram.png",
        )
        def scalars_result(rows):
            mock = MagicMock()
            mock.all.return_value = rows
            return mock

        db = MagicMock()
        db.scalars.side_effect = [
            scalars_result([]),
            scalars_result([]),
            scalars_result([]),
            scalars_result([folder]),
            scalars_result([media]),
        ]
        payload = _build_export_payload(db, user, datetime(2026, 9, 12, tzinfo=timezone.utc))
        self.assertEqual(payload["format"], "storykeep-archive")
        self.assertEqual(payload["folders"][0]["name"], "DAT-325")
        self.assertEqual(len(payload["media"]), 1)


if __name__ == "__main__":
    unittest.main()
