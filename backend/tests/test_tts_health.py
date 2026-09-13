from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.routers.tts import _speech_failure, tts_health


class TtsHealthTests(unittest.TestCase):
    def test_health_reports_bytes_and_elapsed(self):
        with patch("app.services.tts.key_configured", return_value=True), patch(
            "app.services.tts.synthesize", return_value=b"\xff\xf3mp3bytes"
        ):
            body = tts_health(voice_id="eve", user=None)
        self.assertTrue(body["ok"])
        self.assertEqual(body["bytes"], 10)
        self.assertIsInstance(body["ms"], int)

    def test_health_reports_upstream_failure_without_raising(self):
        with patch("app.services.tts.key_configured", return_value=True), patch(
            "app.services.tts.synthesize",
            side_effect=HTTPException(status_code=504, detail="xAI speech service timed out."),
        ):
            body = tts_health(voice_id="eve", user=None)
        self.assertFalse(body["ok"])
        self.assertEqual(body["bytes"], 0)
        self.assertEqual(body["status"], 504)
        self.assertIn("timed out", body["message"])

    def test_health_reports_empty_audio(self):
        with patch("app.services.tts.key_configured", return_value=True), patch(
            "app.services.tts.synthesize", return_value=b""
        ):
            body = tts_health(voice_id="eve", user=None)
        self.assertFalse(body["ok"])
        self.assertEqual(body["bytes"], 0)

    def test_health_without_a_key_is_a_readable_answer(self):
        with patch("app.services.tts.key_configured", return_value=False):
            body = tts_health(voice_id="eve", user=None)
        self.assertFalse(body["ok"])
        self.assertIn("API key", body["message"])

    def test_speech_failure_carries_ok_message_and_detail(self):
        response = _speech_failure(504, "xAI speech service timed out.")
        self.assertEqual(response.status_code, 504)
        body = response.body.decode()
        self.assertIn('"ok":false', body)
        self.assertIn('"message":"xAI speech service timed out."', body)
        self.assertIn('"detail":"xAI speech service timed out."', body)


if __name__ == "__main__":
    unittest.main()
