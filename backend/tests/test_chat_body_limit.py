from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from app.http_limits import CHAT_BODY_MAX_BYTES, PAYLOAD_TOO_LARGE, redact_secrets
from app.main import app, health_payload


class ChatBodyLimitTests(unittest.TestCase):
    def test_redact_strips_xai_keys(self):
        raw = "Authorization: Bearer xai-SECRETKEYVALUE123 failed"
        cleaned = redact_secrets(raw)
        self.assertNotIn("xai-SECRETKEYVALUE123", cleaned)
        self.assertIn("[redacted]", cleaned)

    def test_huge_chat_body_is_413_and_health_stays_200(self):
        client = TestClient(app)
        blob = b"x" * (CHAT_BODY_MAX_BYTES + 50_000)
        response = client.post(
            "/api/v1/chat",
            content=blob,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["detail"], PAYLOAD_TOO_LARGE)
        health = client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["status"], "ok")
        self.assertEqual(health_payload()["status"], "ok")

    def test_chat_message_over_pydantic_max_is_413_not_422(self):
        client = TestClient(app)
        response = client.post("/api/v1/chat", json={"message": "x" * 100_001})
        self.assertEqual(response.status_code, 413)
        self.assertIn("over the cap", response.json()["detail"])
        health = client.get("/health")
        self.assertEqual(health.status_code, 200)

    def test_health_is_ok_after_oversized_include_check(self):
        from fastapi import HTTPException
        from app.services.chat import SEND_CONTEXT_TOO_LARGE, reject_oversized_send

        with self.assertRaises(HTTPException) as caught:
            reject_oversized_send(
                [{"role": "user", "content": "summarize this"}],
                article_body="x" * 96_001,
            )
        self.assertEqual(caught.exception.status_code, 413)
        self.assertEqual(caught.exception.detail, SEND_CONTEXT_TOO_LARGE)
        client = TestClient(app)
        health = client.get("/health")
        self.assertEqual(health.status_code, 200)


if __name__ == "__main__":
    unittest.main()
