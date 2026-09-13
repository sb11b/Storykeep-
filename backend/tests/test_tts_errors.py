import unittest
from unittest.mock import Mock

import httpx

from app.services.tts_errors import raise_for_xai_tts, redact_secrets


class TtsErrorsTests(unittest.TestCase):
    def test_redact_secrets_strips_api_key(self):
        raw = 'Bearer xai-secret12345 and {"key":"xai-abc1234567890"}'
        cleaned = redact_secrets(raw)
        self.assertNotIn("xai-secret12345", cleaned)
        self.assertIn("[redacted]", cleaned)

    def test_raise_for_xai_tts_maps_429(self):
        response = Mock(spec=httpx.Response)
        response.status_code = 429
        response.text = '{"error":{"message":"rate limit exceeded"}}'
        response.json = Mock(return_value={"error": {"message": "rate limit exceeded"}})
        with self.assertRaises(Exception) as ctx:
            raise_for_xai_tts(response, context="test", owner_id="chat-1", chunk_index=0)
        self.assertEqual(ctx.exception.status_code, 429)


if __name__ == "__main__":
    unittest.main()
