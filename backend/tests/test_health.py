from __future__ import annotations

import unittest

from app.main import about_html, health_payload, is_app_shell_alias


class HealthAndLoggedOutShellTests(unittest.TestCase):
    def test_health_payload_has_status_and_build(self):
        body = health_payload()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["build"])
        self.assertIn("built_at", body)

    def test_health_includes_last_rss_fetch_counts(self):
        from app.services import rss as rss_service

        rss_service._record_fetch(status=200, nbytes=4096, item_count=18, url="https://www.newsmax.com/rss/US/18/")
        body = health_payload()
        self.assertEqual(body["rss_status"], "200")
        self.assertEqual(body["rss_bytes"], "4096")
        self.assertEqual(body["rss_item_count"], "18")

    def test_about_html_includes_the_build_hash(self):
        html = about_html()
        body = health_payload()
        self.assertIn("<title>About StoryKeep</title>", html)
        self.assertIn(body["build"], html)
        self.assertIn("/login", html)
        self.assertNotIn("Junior", html)

    def test_archive_is_an_app_shell_alias(self):
        self.assertTrue(is_app_shell_alias("archive"))
        self.assertTrue(is_app_shell_alias("archive/foo"))
        self.assertTrue(is_app_shell_alias("library"))
        self.assertFalse(is_app_shell_alias("login"))
        self.assertFalse(is_app_shell_alias("about"))
        self.assertFalse(is_app_shell_alias(""))


if __name__ == "__main__":
    unittest.main()
