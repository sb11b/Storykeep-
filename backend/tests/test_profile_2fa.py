from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.services import totp_service
from app.services.demo_lock import profile_is_read_only, reject_profile_mutation, user_requires_2fa


class ProfileTwoFactorTests(unittest.TestCase):
    def test_demo_profile_is_read_only(self):
        demo = SimpleNamespace(email="steve@storykeep.local", is_demo_locked=True, totp_enabled=False, email_otp_enabled=False)
        self.assertTrue(profile_is_read_only(demo))
        with self.assertRaises(HTTPException) as caught:
            reject_profile_mutation(demo)
        self.assertEqual(caught.exception.status_code, 403)

    def test_locked_demo_does_not_require_2fa(self):
        demo = SimpleNamespace(email="steve@storykeep.local", is_demo_locked=True, totp_enabled=True, email_otp_enabled=True)
        self.assertFalse(user_requires_2fa(demo))

    def test_live_user_requires_2fa_when_enabled(self):
        live = SimpleNamespace(email="reader@example.com", is_demo_locked=False, totp_enabled=True, email_otp_enabled=False)
        self.assertTrue(user_requires_2fa(live))

    def test_totp_round_trip(self):
        secret = totp_service.generate_totp_secret()
        encrypted = totp_service.encrypt_totp_secret(secret)
        decrypted = totp_service.decrypt_totp_secret(encrypted)
        self.assertEqual(secret, decrypted)
        import pyotp

        current = pyotp.TOTP(secret).now()
        self.assertTrue(totp_service.verify_totp_code(secret, current))

    def test_backup_code_single_use(self):
        codes = totp_service.generate_backup_codes(3)
        hashes = totp_service.hash_backup_codes(codes)
        index = totp_service.verify_backup_code(codes[0], hashes)
        self.assertEqual(index, 0)
        self.assertIsNone(totp_service.verify_backup_code(codes[0], hashes[1:]))


if __name__ == "__main__":
    unittest.main()
