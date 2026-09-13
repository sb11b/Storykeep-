from __future__ import annotations

import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from app.services.demo_lock import email_is_locked, is_locked, reject_authentication, reject_locked


class DemoLockTests(unittest.TestCase):
    def test_published_demo_email_is_locked(self):
        self.assertTrue(email_is_locked("steve@storykeep.local"))
        self.assertTrue(email_is_locked("Steve@Storykeep.local"))
        self.assertFalse(email_is_locked("stevebitsko@duck.com"))
        self.assertFalse(email_is_locked("reader@example.com"))

    def test_flag_or_email_locks_user(self):
        demo = SimpleNamespace(email="steve@storykeep.local", is_demo_locked=False)
        self.assertTrue(is_locked(demo))
        flagged = SimpleNamespace(email="temp@example.com", is_demo_locked=True)
        self.assertTrue(is_locked(flagged))
        live = SimpleNamespace(email="stevebitsko@duck.com", is_demo_locked=True)
        self.assertFalse(is_locked(live))

    def test_reject_locked(self):
        with self.assertRaises(HTTPException) as caught:
            reject_locked(SimpleNamespace(email="steve@storykeep.local", is_demo_locked=True))
        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.detail, "Demo account closed")
        reject_locked(SimpleNamespace(email="stevebitsko@duck.com", is_demo_locked=False))

    def test_reject_authentication_for_session(self):
        with self.assertRaises(HTTPException) as caught:
            reject_authentication(SimpleNamespace(email="steve@storykeep.local", is_demo_locked=True))
        self.assertEqual(caught.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
