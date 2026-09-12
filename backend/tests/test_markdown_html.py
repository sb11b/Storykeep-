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

    def test_equals_signs_are_not_stripped(self):
        html = markdown_to_html("Keep ==the slope== of y.")
        self.assertIn("<mark>the slope</mark>", html)
        self.assertNotIn("==the slope==", html)

    def test_highlight_allows_equals_inside(self):
        html = markdown_to_html("Keep ==a=b== in the formula.")
        self.assertIn("<mark>a=b</mark>", html)

    def test_multiline_highlight_block(self):
        source = "==Line one\n\n• bullet one\n\n• bullet two=="
        html = markdown_to_html(source)
        self.assertIn('<mark class="sk-highlight-block">', html)
        self.assertIn("Line one", html)
        self.assertIn("<li>bullet one</li>", html)
        self.assertNotIn("==", html)

    def test_rejects_remote_image_urls(self):
        html = markdown_to_html("![x](https://evil.example/x.png)")
        self.assertNotIn("<img", html)
        self.assertIn("evil.example", html)

    def test_media_ids(self):
        media = "22222222-2222-2222-2222-222222222222"
        ids = media_ids_in_markdown(f"see ![](/api/v1/media/{media})")
        self.assertEqual([str(item) for item in ids], [media])

    def test_bold_italic_underline_and_lists(self):
        html = markdown_to_html("**bold** *italic*\n<u>under</u>\n- one\n- two\n1. first\n2. second")
        self.assertIn("<strong>bold</strong>", html)
        self.assertIn("<em>italic</em>", html)
        self.assertIn("<u>under</u>", html)
        self.assertIn("<ul>", html)
        self.assertIn("<ol>", html)
        self.assertIn("<li>one</li>", html)
        self.assertIn("<li>first</li>", html)

    def test_inline_text_sizes(self):
        html = markdown_to_html('Intro with <span class="sk-size-lg">big</span> word')
        self.assertIn('<span class="sk-size-lg">big</span>', html)

    def test_fenced_code_preserves_html_and_hash(self):
        source = "```python\nprint('<div>')\n# comment\n```"
        html = markdown_to_html(source)
        self.assertIn('<pre class="sk-code">', html)
        self.assertIn('<span class="sk-code-lang">python</span>', html)
        self.assertIn("data-copy", html)
        self.assertIn("&lt;div&gt;", html)
        self.assertIn("print(", html)
        self.assertIn("# comment", html)
        self.assertNotIn("<div>", html)
        self.assertNotIn("<h1>", html)

    def test_code_fence_skips_markdown_inside(self):
        source = "```text\n==no highlight==\n# not heading\n```"
        html = markdown_to_html(source)
        self.assertIn("==no highlight==", html)
        self.assertIn("# not heading", html)
        self.assertNotIn("<mark>", html)
        self.assertNotIn("<h1>", html)

    def test_wikilinks_render_as_buttons(self):
        html = markdown_to_html("See [[Other Note|label]] and [[Missing]]")
        self.assertIn('class="wikilink wikilink-missing"', html)
        self.assertIn('data-wikilink-target="Other Note"', html)
        self.assertIn("label", html)
        self.assertIn('data-wikilink-target="Missing"', html)

    def test_wikilinks_skip_code_fences(self):
        source = "Before [[Link]]\n```text\n[[Not a link]]\n```"
        html = markdown_to_html(source)
        self.assertIn('data-wikilink-target="Link"', html)
        self.assertIn("[[Not a link]]", html)
        self.assertNotIn('data-wikilink-target="Not a link"', html)


if __name__ == "__main__":
    unittest.main()
