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

    def test_tts_read_timeout_default(self):
        timeout = tts_service.tts_timeout()
        self.assertEqual(timeout.read, 120.0)

    def test_default_voice_is_castor(self):
        with patch.object(tts_service.settings, "xai_tts_voice", ""):
            self.assertEqual(tts_service.default_voice(), "castor")

    def test_order_voices_castor_first_not_altair(self):
        ordered = tts_service.order_voices_for_ui(
            [
                {"voice_id": "altair", "name": "Altair"},
                {"voice_id": "castor", "name": "castor"},
                {"voice_id": "eve", "name": "Eve"},
            ]
        )
        self.assertEqual(ordered[0]["voice_id"], "castor")
        self.assertEqual(ordered[0]["name"], "Castor")

    def test_streaming_payload_uses_optimize_streaming_latency(self):
        payload = tts_service.streaming_payload("Hello", "castor")
        self.assertEqual(payload["voice_id"], "castor")
        self.assertEqual(payload["language"], "en")
        self.assertEqual(payload["optimize_streaming_latency"], 1)
        self.assertIsInstance(payload["optimize_streaming_latency"], int)


if __name__ == "__main__":
    unittest.main()
