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


if __name__ == "__main__":
    unittest.main()
