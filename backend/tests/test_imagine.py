from __future__ import annotations

import base64
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.services.imagine import (
    _imagine_hits,
    assistant_edit_markdown,
    assistant_image_markdown,
    assistant_inspired_markdown,
    decode_b64_image,
    edit_image_bytes,
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
        self.assertNotIn("Here's the image.", text)
        self.assertIn(f'<img src="/api/v1/media/{media_id}"', text)
        self.assertIn('alt="a red notebook on a desk"', text)
        edited = assistant_edit_markdown("make me look older", media_id)
        self.assertNotIn("Here's the edited image.", edited)
        self.assertIn(f'<img src="/api/v1/media/{media_id}"', edited)
        inspired = assistant_inspired_markdown("older portrait", media_id)
        self.assertIn("Inspired by your photo", inspired)
        self.assertIn(f'<img src="/api/v1/media/{media_id}"', inspired)
        self.assertNotIn("FaceApp", inspired)

    def test_edit_image_posts_owned_data_uri(self):
        out = b"\x89PNG\r\n\x1a\n" + b"older"
        encoded_out = base64.b64encode(out).decode("ascii")
        data_url = "data:image/jpeg;base64,abc"
        captured: dict = {}

        class FakeResp:
            status_code = 200

            def json(self):
                return {"data": [{"b64_json": encoded_out}]}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, url, headers=None, json=None):
                captured["url"] = url
                captured["json"] = json
                return FakeResp()

        with patch("app.services.imagine.httpx.Client", FakeClient):
            with patch("app.services.imagine.require_imagine_key", return_value="xai-test"):
                payload = edit_image_bytes("make me look older", data_url)
        self.assertEqual(payload, out)
        self.assertTrue(str(captured["url"]).endswith("/images/edits"))
        self.assertEqual(captured["json"]["image"]["url"], data_url)
        self.assertEqual(captured["json"]["image"]["type"], "image_url")
        self.assertNotIn("http://", captured["json"]["image"]["url"])

    def test_edit_image_rejects_remote_urls(self):
        with self.assertRaises(HTTPException) as raised:
            edit_image_bytes("make me look older", "https://example.com/selfie.jpg")
        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("uploaded in this thread", raised.exception.detail)

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
        raw = b"\xff\xd8\xff" + b"jpeg-bytes"
        encoded = base64.b64encode(raw).decode("ascii")
        payload = extract_image_bytes({"data": [{"b64_json": encoded}]})
        self.assertEqual(payload, raw)

    def test_reject_svg_and_mock_passing_graphic(self):
        from app.services.imagine import require_raster_image

        with self.assertRaises(HTTPException) as raised:
            require_raster_image(b'<svg xmlns="http://www.w3.org/2000/svg">implemented and passing</svg>')
        self.assertEqual(raised.exception.status_code, 502)
        self.assertEqual(raised.exception.detail, "Could not generate that image.")
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        self.assertEqual(require_raster_image(png)[:8], b"\x89PNG\r\n\x1a\n")
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
