from __future__ import annotations

import inspect
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.http_limits import redact_secrets
from app.main import http_exception_with_message
from app.routers import stt as stt_router
from app.services import stt_clip
from app.services.stt_limits import clear_stt_rate_limits

WAV = b"RIFF" + b"\x00" * 60
_RealClient = httpx.Client


def _app(user: SimpleNamespace) -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(StarletteHTTPException, http_exception_with_message)
    app.include_router(stt_router.router, prefix="/api/v1")

    def fake_db():
        yield MagicMock()

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_user] = lambda: user
    return app


class SttClipTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_stt_rate_limits()
        self._key = settings.xai_api_key
        settings.xai_api_key = "xai-test-key-not-real"

    def tearDown(self) -> None:
        settings.xai_api_key = self._key
        clear_stt_rate_limits()

    def test_demo_forbidden(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4(), email="steve@storykeep.local", is_demo_locked=True)
        client = TestClient(_app(user))
        response = client.post("/api/v1/stt", files={"file": ("clip.wav", WAV, "audio/wav")})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "STT is not enabled on this account")
        self.assertNotEqual(response.status_code, 500)

    def test_empty_blob(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4(), email="steve@example.com", is_demo_locked=False)
        client = TestClient(_app(user))
        response = client.post("/api/v1/stt", files={"file": ("clip.webm", b"tiny", "audio/webm")})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "empty blob")

    def test_missing_key(self) -> None:
        settings.xai_api_key = ""
        user = SimpleNamespace(id=uuid.uuid4(), email="steve@example.com", is_demo_locked=False)
        client = TestClient(_app(user))
        response = client.post("/api/v1/stt", files={"file": ("clip.wav", WAV, "audio/wav")})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "STT failed (503)")

    def test_success_transcript(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4(), email="steve@example.com", is_demo_locked=False)

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertTrue(request.headers.get("authorization", "").startswith("Bearer "))
            self.assertNotIn(b"xai-test-key-not-real", request.content or b"")
            body = request.content.decode("utf-8", errors="ignore")
            self.assertIn("grok-voice-transcribe-2.0", body)
            self.assertIn("language", body)
            return httpx.Response(200, json={"text": "hello Junior", "duration": 1.2})

        class FakeClient:
            def __init__(self, *args, **kwargs):
                self._client = _RealClient(transport=httpx.MockTransport(handler))

            def __enter__(self):
                return self._client

            def __exit__(self, *args):
                self._client.close()

        with patch("app.services.stt_clip.httpx.Client", FakeClient):
            client = TestClient(_app(user))
            response = client.post("/api/v1/stt", files={"file": ("clip.wav", WAV, "audio/wav")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "hello Junior")

    def test_empty_transcript_returns_200(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4(), email="steve@example.com", is_demo_locked=False)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"text": "   ", "duration": 1.0})

        class FakeClient:
            def __init__(self, *args, **kwargs):
                self._client = _RealClient(transport=httpx.MockTransport(handler))

            def __enter__(self):
                return self._client

            def __exit__(self, *args):
                self._client.close()

        with patch("app.services.stt_clip.httpx.Client", FakeClient):
            client = TestClient(_app(user))
            response = client.post("/api/v1/stt", files={"file": ("audio.wav", WAV, "audio/wav")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "")
        self.assertEqual(response.json()["error"], "empty transcript")

    def test_results_transcript_shape(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4(), email="steve@example.com", is_demo_locked=False)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"results": [{"transcript": "from results array"}]},
            )

        class FakeClient:
            def __init__(self, *args, **kwargs):
                self._client = _RealClient(transport=httpx.MockTransport(handler))

            def __enter__(self):
                return self._client

            def __exit__(self, *args):
                self._client.close()

        with patch("app.services.stt_clip.httpx.Client", FakeClient):
            client = TestClient(_app(user))
            response = client.post("/api/v1/stt", files={"file": ("audio.wav", WAV, "audio/wav")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["text"], "from results array")

    def test_upstream_401(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4(), email="steve@example.com", is_demo_locked=False)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": "bad key"})

        class FakeClient:
            def __init__(self, *args, **kwargs):
                self._client = _RealClient(transport=httpx.MockTransport(handler))

            def __enter__(self):
                return self._client

            def __exit__(self, *args):
                self._client.close()

        with patch("app.services.stt_clip.httpx.Client", FakeClient):
            client = TestClient(_app(user))
            response = client.post("/api/v1/stt", files={"file": ("clip.webm", WAV, "audio/webm")})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "STT failed (401)")

    def test_status_clip_mode(self) -> None:
        user = SimpleNamespace(id=uuid.uuid4(), email="steve@example.com", is_demo_locked=False)
        client = TestClient(_app(user))
        response = client.get("/api/v1/stt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mode"], "clip")
        self.assertEqual(response.json()["provider"], "xai")
        self.assertTrue(response.json()["enabled"])

    def test_source_does_not_log_audio(self) -> None:
        source = inspect.getsource(stt_clip)
        self.assertIn("stt clip bytes=%s type=%s", source)
        self.assertNotIn("logger.info(data", source)
        self.assertNotIn("logger.info(payload", source)
        redacted = redact_secrets("token=xai-abcd1234secret")
        self.assertNotIn("xai-abcd1234secret", redacted)


if __name__ == "__main__":
    unittest.main()
