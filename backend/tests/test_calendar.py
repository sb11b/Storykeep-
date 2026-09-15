from __future__ import annotations

import unittest

from app.services.calendar_tool import extract_calendar_proposal, normalize_add_event
from app.services.google_oauth import CALENDAR_EVENTS_SCOPE, assert_calendar_scope_only, authorize_url


class CalendarToolTests(unittest.TestCase):
    def test_normalizes_add_event(self):
        found = normalize_add_event(
            {"title": "Office hours", "start": "2026-09-16T15:00:00-04:00", "end": "2026-09-16T16:00:00-04:00"}
        )
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found["title"], "Office hours")
        self.assertIn("2026-09-16T15:00:00", found["start"])

    def test_assembles_streaming_tool_call(self):
        from app.services.calendar_tool import assemble_tool_calls

        found = assemble_tool_calls(
            [
                {"index": 0, "function": {"name": "add_event", "arguments": ""}},
                {"index": 0, "function": {"arguments": '{"title":"Standup","start":"2026-09-16T09:00:00-04:00","end":"2026-09-16T09:15:00-04:00"}'}},
            ]
        )
        self.assertEqual(found["title"], "Standup")
        text = """Sure.\n```storykeep-event\n{"title":"Lab","start":"2026-09-16T10:00:00-04:00","end":"2026-09-16T11:00:00-04:00"}\n```\n"""
        found = extract_calendar_proposal(text)
        self.assertEqual(found["title"], "Lab")

    def test_oauth_url_is_calendar_scope_only(self):
        from app.config import settings

        prev_id = settings.google_client_id
        prev_secret = settings.google_client_secret
        settings.google_client_id = "client.apps.googleusercontent.com"
        settings.google_client_secret = "secret"
        try:
            url = authorize_url(origin="https://storykeep.example", state="abc")
        finally:
            settings.google_client_id = prev_id
            settings.google_client_secret = prev_secret
        self.assertIn("calendar.events", url)
        self.assertNotIn("gmail", url.lower())
        self.assertNotIn("imap", url.lower())
        self.assertEqual(CALENDAR_EVENTS_SCOPE, "https://www.googleapis.com/auth/calendar.events")

    def test_rejects_gmail_scope(self):
        from fastapi import HTTPException

        with self.assertRaises(HTTPException):
            assert_calendar_scope_only("https://www.googleapis.com/auth/gmail.readonly")

    def test_tokens_round_trip_encrypted(self):
        from app.services.crypto_box import decrypt_secret, encrypt_secret

        token = "ya29.secret-calendar-token"
        blob = encrypt_secret(token)
        self.assertNotIn("ya29.", blob)
        self.assertEqual(decrypt_secret(blob), token)

    def test_demo_cannot_connect(self):
        from types import SimpleNamespace
        from fastapi import HTTPException
        from app.services.demo_lock import reject_locked

        with self.assertRaises(HTTPException) as caught:
            reject_locked(SimpleNamespace(email="steve@storykeep.local", is_demo_locked=True))
        self.assertEqual(caught.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
