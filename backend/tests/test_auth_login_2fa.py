from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.services import totp_service
from app.services.demo_lock import user_requires_2fa


class AuthLoginTwoFactorTests(unittest.TestCase):
    def test_user_without_2fa_does_not_require_challenge(self):
        user = SimpleNamespace(email="reader@example.com", is_demo_locked=False, totp_enabled=False, email_otp_enabled=False)
        self.assertFalse(user_requires_2fa(user))

    def test_totp_user_requires_challenge_unless_demo_locked(self):
        user = SimpleNamespace(email="reader@example.com", is_demo_locked=False, totp_enabled=True, email_otp_enabled=False)
        self.assertTrue(user_requires_2fa(user))

    def test_backup_code_consumed_after_verify(self):
        codes = totp_service.generate_backup_codes(2)
        hashes = totp_service.hash_backup_codes(codes)
        index = totp_service.verify_backup_code(codes[0], hashes)
        self.assertEqual(index, 0)
        remaining = hashes[:index] + hashes[index + 1 :]
        self.assertIsNone(totp_service.verify_backup_code(codes[0], remaining))


if __name__ == "__main__":
    unittest.main()
