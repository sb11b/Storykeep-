from __future__ import annotations

import unittest

from app.services.markdown_html import markdown_to_html


class ComposedNoteMarkdownTests(unittest.TestCase):
    def test_bullet_markdown_renders_as_list(self):
        body = "Intro line\n- first item\n- second item"
        html = markdown_to_html(body)
        self.assertIn("<ul>", html)
        self.assertIn("<li>first item</li>", html)
        self.assertIn("<li>second item</li>", html)


if __name__ == "__main__":
    unittest.main()
