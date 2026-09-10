from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.config import Settings


class BackupB2ConfigTests(unittest.TestCase):
    def test_b2_bucket_maps_to_object_bucket(self):
        settings = Settings(
            b2_bucket="keep-archive",
            b2_region="us-west-004",
            b2_endpoint="https://s3.us-west-004.backblazeb2.com",
            s3_bucket=None,
        )
        self.assertEqual(settings.object_bucket, "keep-archive")
        self.assertEqual(settings.object_region, "us-west-004")

    def test_endpoint_without_scheme_gets_https(self):
        from app.services import backup as backup_service

        with patch.object(backup_service.settings, "b2_endpoint", "s3.us-east-005.backblazeb2.com"):
            self.assertEqual(
                backup_service._b2_endpoint_url(),
                "https://s3.us-east-005.backblazeb2.com",
            )
        settings = Settings(s3_bucket="legacy-bucket", b2_bucket=None, b2_region="")
        self.assertEqual(settings.object_bucket, "legacy-bucket")
        self.assertEqual(settings.object_region, "us-east-1")

    def test_upload_uses_b2_endpoint_and_prefix(self):
        from app.services import backup as backup_service
        from pathlib import Path

        fake = MagicMock()
        with (
            patch.object(backup_service.settings, "b2_bucket", "keep-archive"),
            patch.object(backup_service.settings, "s3_bucket", None),
            patch.object(backup_service.settings, "s3_prefix", "storykeep"),
            patch.object(backup_service.settings, "b2_endpoint", "https://s3.example.invalid"),
            patch.object(backup_service.settings, "b2_key_id", "kid"),
            patch.object(backup_service.settings, "b2_application_key", "secret"),
            patch.object(backup_service.settings, "b2_region", "us-west-004"),
            patch.object(backup_service.settings, "aws_region", "us-east-1"),
            patch.object(backup_service, "_object_store_client", return_value=fake),
        ):
            path = Path("/tmp/storykeep-probe.json")
            location = backup_service._maybe_upload_s3(path)
        fake.upload_file.assert_called_once_with(str(path), "keep-archive", "storykeep/storykeep-probe.json")
        self.assertEqual(location, "s3://keep-archive/storykeep/storykeep-probe.json")


if __name__ == "__main__":
    unittest.main()
