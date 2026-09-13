from __future__ import annotations

import unittest

from app.services import rss


class RssImageTests(unittest.TestCase):
    def test_entry_image_prefers_media_thumbnail(self):
        entry = {
            "media_thumbnail": [{"url": "https://static.foxnews.com/thumb.jpg"}],
            "enclosures": [{"href": "https://example.com/audio.mp3", "type": "audio/mpeg"}],
        }
        self.assertEqual(rss._entry_image(entry), "https://static.foxnews.com/thumb.jpg")

    def test_entry_image_accepts_media_content_without_explicit_type(self):
        entry = {
            "media_content": [{"url": "https://static.foxnews.com/photo.jpg", "medium": "image"}],
        }
        self.assertEqual(rss._entry_image(entry), "https://static.foxnews.com/photo.jpg")

    def test_entry_image_accepts_image_enclosure(self):
        entry = {
            "enclosures": [{"href": "https://cdn.example.com/hero.png", "type": "image/png"}],
        }
        self.assertEqual(rss._entry_image(entry), "https://cdn.example.com/hero.png")

    def test_entry_image_resolves_relative_url_against_entry_link(self):
        entry = {
            "link": "https://www.cbr.com/naruto-strongest-characters/",
            "media_content": [{"url": "/wp-content/uploads/hero.jpg", "medium": "image"}],
        }
        self.assertEqual(
            rss._entry_image(entry),
            "https://www.cbr.com/wp-content/uploads/hero.jpg",
        )

    def test_entry_image_resolves_protocol_relative_url(self):
        entry = {
            "link": "https://www.cbr.com/story/",
            "media_thumbnail": [{"url": "//static0.cbrimages.com/thumb.jpg"}],
        }
        self.assertEqual(rss._entry_image(entry), "https://static0.cbrimages.com/thumb.jpg")

    def test_entry_image_for_falls_back_to_first_body_image(self):
        entry = {"link": "https://www.cbr.com/story/"}
        html = '<p>Lead</p><img src="/images/inline.jpg">'
        self.assertEqual(
            rss.entry_image_for(entry, "https://www.cbr.com/story/", html, None),
            "https://www.cbr.com/images/inline.jpg",
        )

    def test_entry_image_for_returns_none_without_any_art(self):
        entry = {"link": "https://www.cbr.com/story/"}
        self.assertIsNone(rss.entry_image_for(entry, "https://www.cbr.com/story/", "<p>No art</p>", None))


if __name__ == "__main__":
    unittest.main()
