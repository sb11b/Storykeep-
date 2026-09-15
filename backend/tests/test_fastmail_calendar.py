from __future__ import annotations

import unittest

from app.services.fastmail_caldav import (
    DEFAULT_CALDAV,
    NO_CALENDARS,
    build_vevent,
    calendar_query_xml,
    calendars_from_listing,
    caldav_origin,
    decode_event_id,
    encode_event_id,
    normalize_calendar_url,
    parse_prop_href,
    parse_vevents,
    pick_calendar,
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
        self.assertNotIn("google", joined)
        self.assertNotIn("/callback", joined)

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

    def test_principal_href_is_not_the_request_url(self):
        xml = """<?xml version="1.0"?>
        <D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
          <D:response>
            <D:href>/.well-known/caldav</D:href>
            <D:propstat>
              <D:prop>
                <D:current-user-principal>
                  <D:href>/dav/principals/user/steve@fastmail.com/</D:href>
                </D:current-user-principal>
              </D:prop>
            </D:propstat>
          </D:response>
        </D:multistatus>
        """
        self.assertEqual(
            parse_prop_href(xml, "current-user-principal"),
            "/dav/principals/user/steve@fastmail.com/",
        )

    def test_calendar_home_href_is_not_the_principal(self):
        xml = """<?xml version="1.0"?>
        <D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
          <D:response>
            <D:href>/dav/principals/user/steve@fastmail.com/</D:href>
            <D:propstat>
              <D:prop>
                <C:calendar-home-set>
                  <D:href>/dav/calendars/user/steve@fastmail.com/</D:href>
                </C:calendar-home-set>
              </D:prop>
            </D:propstat>
          </D:response>
        </D:multistatus>
        """
        self.assertEqual(
            parse_prop_href(xml, "calendar-home-set"),
            "/dav/calendars/user/steve@fastmail.com/",
        )

    def test_lists_one_calendar_under_home(self):
        home = "https://caldav.fastmail.com/dav/calendars/user/steve@fastmail.com/"
        xml = f"""<?xml version="1.0"?>
        <D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
          <D:response>
            <D:href>/dav/calendars/user/steve@fastmail.com/</D:href>
            <D:propstat><D:prop>
              <D:displayname>Calendars</D:displayname>
              <D:resourcetype><D:collection/></D:resourcetype>
            </D:prop></D:propstat>
          </D:response>
          <D:response>
            <D:href>/dav/calendars/user/steve@fastmail.com/aabbccdd/</D:href>
            <D:propstat><D:prop>
              <D:displayname>Calendar</D:displayname>
              <D:resourcetype><D:collection/><C:calendar/></D:resourcetype>
              <C:supported-calendar-component-set><C:comp name="VEVENT"/></C:supported-calendar-component-set>
            </D:prop></D:propstat>
          </D:response>
        </D:multistatus>
        """
        found = calendars_from_listing(xml, home)
        self.assertEqual(len(found), 1)
        chosen = pick_calendar(found)
        self.assertIsNotNone(chosen)
        assert chosen is not None
        self.assertTrue(chosen["href"].endswith("/aabbccdd/"))
        self.assertEqual(chosen["name"], "Calendar")

    def test_empty_listing_uses_create_on_fastmail_copy(self):
        from fastapi import HTTPException

        self.assertEqual(NO_CALENDARS, "No calendars — create one on Fastmail.com")
        self.assertNotIn("invalid", NO_CALENDARS.lower())
        self.assertNotIn("account", NO_CALENDARS.lower())
        found = calendars_from_listing(
            """<?xml version="1.0"?><D:multistatus xmlns:D="DAV:"></D:multistatus>""",
            "https://caldav.fastmail.com/dav/calendars/user/steve@fastmail.com/",
        )
        self.assertEqual(found, [])
        with self.assertRaises(HTTPException) as caught:
            raise HTTPException(status_code=409, detail=NO_CALENDARS)
        self.assertEqual(caught.exception.status_code, 409)

    def test_pasted_calendar_url_stays_on_fastmail_host(self):
        url = normalize_calendar_url(
            "https://caldav.fastmail.com/dav/calendars/user/steve@fastmail.com/aabbccdd/",
            email="steve@fastmail.com",
        )
        self.assertEqual(
            url,
            "https://caldav.fastmail.com/dav/calendars/user/steve@fastmail.com/aabbccdd/",
        )
        from fastapi import HTTPException

        with self.assertRaises(HTTPException):
            normalize_calendar_url("https://evil.example/dav/", email="steve@fastmail.com")

    def test_vevent_stores_location_url_and_color(self):
        ics = build_vevent(
            uid="zoom@storykeep",
            title="Zoom",
            start="2026-09-16T15:00:00-04:00",
            end="2026-09-16T16:00:00-04:00",
            location="Online",
            meeting_url="https://zoom.example/j/1",
            online=True,
            color="#DC2626",
        )
        self.assertIn("LOCATION:Online", ics)
        self.assertIn("URL:https://zoom.example/j/1", ics)
        self.assertIn("COLOR:#DC2626", ics)
        self.assertIn("X-APPLE-CALENDAR-COLOR:#DC2626", ics)
        found = parse_vevents(ics)
        self.assertTrue(found[0]["online"])
        self.assertEqual(found[0]["color"], "#DC2626")
        office = build_vevent(
            uid="office@storykeep",
            title="Office hours",
            start="2026-09-16T10:00:00-04:00",
            end="2026-09-16T11:00:00-04:00",
            location="12 Main St, Boston",
            color="#2563EB",
        )
        parsed = parse_vevents(office)[0]
        self.assertEqual(parsed["location"], "12 Main St, Boston")
        self.assertEqual(parsed["color"], "#2563EB")
        self.assertNotEqual(parsed["color"], found[0]["color"])


if __name__ == "__main__":
    unittest.main()
