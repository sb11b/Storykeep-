from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from app.services.demo_lock import email_is_locked, reject_authentication


class DemoAuthTests(unittest.TestCase):
    def test_demo_email_is_locked(self):
        self.assertTrue(email_is_locked("steve@storykeep.local"))
        self.assertFalse(email_is_locked("angry.tune8751@fastmail.com"))

    def test_reject_authentication_blocks_demo_user(self):
        demo = SimpleNamespace(email="steve@storykeep.local", is_demo_locked=True)
        with self.assertRaises(HTTPException) as caught:
            reject_authentication(demo)
        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(caught.exception.detail, "Demo account closed")

    def test_reject_authentication_allows_real_user(self):
        live = SimpleNamespace(email="angry.tune8751@fastmail.com", is_demo_locked=False)
        reject_authentication(live)

    def test_reject_authentication_allows_none(self):
        reject_authentication(None)


if __name__ == "__main__":
    unittest.main()
