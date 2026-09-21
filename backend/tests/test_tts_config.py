from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import tts as tts_service


class TtsConfigTests(unittest.TestCase):
    def test_default_voice_from_settings(self):
        with patch.object(tts_service.settings, "xai_tts_voice", "castor"):
            self.assertEqual(tts_service.default_voice(), "castor")

    def test_tts_url_from_settings(self):
        with patch.object(tts_service.settings, "xai_tts_url", "https://api.x.ai/v1/tts"):
            self.assertEqual(tts_service.tts_url(), "https://api.x.ai/v1/tts")
            self.assertEqual(tts_service.voices_url(), "https://api.x.ai/v1/tts/voices")


if __name__ == "__main__":
    unittest.main()
