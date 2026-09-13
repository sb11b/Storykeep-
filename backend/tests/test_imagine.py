from __future__ import annotations

import base64
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.services.imagine import (
    _imagine_hits,
    assistant_image_markdown,
    decode_b64_image,
    enforce_imagine_rate_limit,
    extract_image_bytes,
    image_alt,
    map_imagine_http_error,
    normalize_prompt,
)


class ImagineServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        _imagine_hits.clear()

    def test_normalize_prompt_collapses_whitespace(self):
        self.assertEqual(normalize_prompt("  a red   notebook \n on a desk  "), "a red notebook on a desk")
        self.assertEqual(normalize_prompt("   "), "")

    def test_image_alt_strips_markdown_punct(self):
        self.assertEqual(image_alt("a [red] notebook (desk)"), "a red notebook desk")
        self.assertTrue(len(image_alt("x" * 200)) <= 80)

    def test_assistant_markdown_uses_media_url(self):
        media_id = uuid4()
        text = assistant_image_markdown("a red notebook on a desk", media_id)
        self.assertIn("Here's the image.", text)
        self.assertIn(f"/api/v1/media/{media_id}", text)
        self.assertIn("![a red notebook on a desk]", text)

    def test_decode_b64_accepts_data_uri(self):
        raw = b"\x89PNG\r\n\x1a\n" + b"hello"
        encoded = base64.b64encode(raw).decode("ascii")
        self.assertEqual(decode_b64_image(f"data:image/png;base64,{encoded}"), raw)
        self.assertEqual(decode_b64_image(encoded), raw)

    def test_decode_b64_rejects_empty(self):
        with self.assertRaises(HTTPException) as raised:
            decode_b64_image("")
        self.assertEqual(raised.exception.status_code, 502)
        self.assertIn("did not return an image", raised.exception.detail)

    def test_extract_image_bytes_from_b64(self):
        raw = b"\xff\xd8\xff" + b"jpeg"
        encoded = base64.b64encode(raw).decode("ascii")
        payload = extract_image_bytes({"data": [{"b64_json": encoded}]})
        self.assertEqual(payload, raw)

    def test_extract_image_bytes_missing_data(self):
        with self.assertRaises(HTTPException) as raised:
            extract_image_bytes({"data": []})
        self.assertEqual(raised.exception.status_code, 502)

    def test_rate_limit_is_ten_per_hour(self):
        user = uuid4()
        now = 1_000_000.0
        for index in range(10):
            enforce_imagine_rate_limit(user, now=now + index)
        with self.assertRaises(HTTPException) as raised:
            enforce_imagine_rate_limit(user, now=now + 11)
        self.assertEqual(raised.exception.status_code, 429)
        self.assertIn("10 per hour", raised.exception.detail)
        enforce_imagine_rate_limit(user, now=now + 3601)

    def test_maps_auth_and_rate_errors(self):
        auth = map_imagine_http_error(401, "nope", "grok-imagine-image-2.0")
        self.assertEqual(auth.status_code, 401)
        self.assertEqual(auth.detail, "xAI auth failed")
        limited = map_imagine_http_error(429, "slow down", "grok-imagine-image-2.0")
        self.assertEqual(limited.status_code, 429)
        self.assertIn("rate-limiting", limited.detail)

    def test_attach_to_message_still_rejects_assistant_by_default(self):
        from app.services.chat_attachments import attach_to_message

        with self.assertRaises(HTTPException) as raised:
            attach_to_message(
                SimpleNamespace(),
                SimpleNamespace(),
                SimpleNamespace(role="assistant", id=uuid4()),
                [uuid4()],
            )
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("your message", raised.exception.detail)

    def test_vision_on_grok_46_includes_image_url(self):
        from app.services.chat import messages_for_xai

        history = [
            {
                "role": "user",
                "content": "what is in this photo",
                "files": [
                    {
                        "media_id": str(uuid4()),
                        "filename": "desk.jpg",
                        "kind": "image",
                        "content_type": "image/jpeg",
                    }
                ],
            }
        ]
        parts = [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,abc", "detail": "auto"}}]
        with patch("app.services.chat_attachments.vision_parts", return_value=parts):
            prepared = messages_for_xai(history, model="grok-4.6", db=object(), user=object())
        content = prepared[-1]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[1]["type"], "image_url")
        self.assertIn("desk.jpg", content[0]["text"])


if __name__ == "__main__":
    unittest.main()
