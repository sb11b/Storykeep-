from __future__ import annotations

import unittest

from app.services.markdown_html import markdown_to_html
from app.services.note_media import media_ids_in_markdown


class MarkdownHtmlTests(unittest.TestCase):
    def test_highlight_and_safe_image(self):
        media = "11111111-1111-1111-1111-111111111111"
        html = markdown_to_html(f"==keep this==\n![diagram](/api/v1/media/{media})")
        self.assertIn("<mark>keep this</mark>", html)
        self.assertIn(f'<img src="/api/v1/media/{media}" alt="diagram" />', html)

    def test_rejects_remote_image_urls(self):
        html = markdown_to_html("![x](https://evil.example/x.png)")
        self.assertNotIn("<img", html)
        self.assertIn("evil.example", html)

    def test_media_ids(self):
        media = "22222222-2222-2222-2222-222222222222"
        ids = media_ids_in_markdown(f"see ![](/api/v1/media/{media})")
        self.assertEqual([str(item) for item in ids], [media])


if __name__ == "__main__":
    unittest.main()
