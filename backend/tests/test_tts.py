from __future__ import annotations

import unittest

from app.services.tts import speech_plain, spoken_title, word_count


class SpeechPlainTests(unittest.TestCase):
    def test_skips_highlight_markers_and_images(self):
        html = '<p>The <mark>derivative</mark> is the slope.</p><img alt="plot" src="/api/v1/media/11111111-1111-1111-1111-111111111111" />'
        self.assertEqual(speech_plain(html), "The derivative is the slope.")
        md = "The ==derivative== is the slope.\n![plot](/api/v1/media/11111111-1111-1111-1111-111111111111)"
        self.assertEqual(speech_plain(md), "The derivative is the slope.")
        self.assertNotIn("==", speech_plain(md))
        self.assertNotIn("plot", speech_plain(md))

    def test_title_word_count_matches_spoken_title(self):
        self.assertEqual(word_count(spoken_title("Note highlights demo")), 3)


if __name__ == "__main__":
    unittest.main()
