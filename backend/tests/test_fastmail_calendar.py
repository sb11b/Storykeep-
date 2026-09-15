from __future__ import annotations

import unittest

from app.services.fastmail_caldav import (
    DEFAULT_CALDAV,
    build_vevent,
    calendar_query_xml,
    caldav_origin,
    decode_event_id,
    encode_event_id,
    parse_vevents,
    time_range_ics,
)


class FastmailCalDavTests(unittest.TestCase):
    def test_origin_defaults_when_env_blank(self):
        from app.config import settings

        previous = settings.fastmail_caldav_url
        settings.fastmail_caldav_url = ""
        try:
            self.assertEqual(caldav_origin(), DEFAULT_CALDAV)
        finally:
            settings.fastmail_caldav_url = previous

    def test_parses_vevent_and_round_trips_ics(self):
        ics = build_vevent(
            uid="abc@storykeep",
            title="Office hours",
            start="2026-09-16T15:00:00-04:00",
            end="2026-09-16T16:00:00-04:00",
        )
        self.assertIn("SUMMARY:Office hours", ics)
        found = parse_vevents(ics)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["title"], "Office hours")
        self.assertIn("2026-09-16T19:00:00", str(found[0]["start"]))

    def test_event_id_codec(self):
        href = "https://caldav.fastmail.com/dav/calendars/user/steve@fastmail.com/calendar/abc.ics"
        packed = encode_event_id(href)
        self.assertTrue(packed.startswith("fm-"))
        self.assertEqual(decode_event_id(packed), href)

    def test_calendar_query_uses_utc_range(self):
        xml = calendar_query_xml("2026-09-14T00:00:00-04:00", "2026-09-21T00:00:00-04:00")
        self.assertIn("time-range", xml)
        self.assertIn(time_range_ics("2026-09-14T00:00:00-04:00"), xml)
        self.assertNotIn("jmap", xml.lower())

    def test_tokens_encrypt_and_are_not_plaintext(self):
        from app.services.crypto_box import decrypt_secret, encrypt_secret

        token = "fastmail-app-password-example"
        blob = encrypt_secret(token)
        self.assertNotIn("fastmail-app-password", blob)
        self.assertEqual(decrypt_secret(blob), token)

    def test_calendar_router_has_no_mail_inbox(self):
        from app.routers import calendar as calendar_router

        paths = [getattr(route, "path", "") for route in calendar_router.router.routes]
        joined = " ".join(paths).lower()
        self.assertIn("/fastmail/connect", joined)
        self.assertNotIn("jmap", joined)
        self.assertNotIn("imap", joined)
        self.assertNotIn("inbox", joined)

    def test_status_configured_without_fastmail_env(self):
        from app.config import settings

        self.assertTrue(settings.fastmail_calendar_configured)
        previous = settings.fastmail_caldav_url
        settings.fastmail_caldav_url = ""
        try:
            self.assertTrue(settings.fastmail_calendar_configured)
            self.assertEqual(caldav_origin(), DEFAULT_CALDAV)
        finally:
            settings.fastmail_caldav_url = previous


if __name__ == "__main__":
    unittest.main()
