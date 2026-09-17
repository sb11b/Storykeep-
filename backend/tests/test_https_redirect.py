from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings
from app.https_redirect import HttpsRedirectMiddleware, forwarded_proto


async def _ok_app(scope, receive, send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/plain")],
        }
    )
    await send({"type": "http.response.body", "body": b"ok"})


def _run(app, path: str, headers: list[tuple[bytes, bytes]], scheme: str = "http") -> list[dict]:
    sent: list[dict] = []

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": scheme,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 123),
        "server": ("127.0.0.1", 8080),
    }
    asyncio.run(app(scope, receive, send))
    return sent


class HttpsRedirectTests(unittest.TestCase):
    def test_production_trusts_forwarded_https_without_redirect(self):
        app = HttpsRedirectMiddleware(_ok_app, enabled=True)
        sent = _run(
            app,
            "/",
            [(b"host", b"storykeep.example"), (b"x-forwarded-proto", b"https")],
        )
        self.assertEqual(sent[0]["status"], 200)

    def test_production_http_redirects_to_https(self):
        app = HttpsRedirectMiddleware(_ok_app, enabled=True)
        sent = _run(app, "/login", [(b"host", b"storykeep.example")])
        self.assertEqual(sent[0]["status"], 308)
        headers = dict(sent[0]["headers"])
        self.assertEqual(headers[b"location"], b"https://storykeep.example/login")

    def test_health_stays_http_for_railway_check(self):
        app = HttpsRedirectMiddleware(_ok_app, enabled=True)
        sent = _run(app, "/health", [(b"host", b"127.0.0.1:8080")])
        self.assertEqual(sent[0]["status"], 200)

    def test_disabled_does_not_redirect(self):
        app = HttpsRedirectMiddleware(_ok_app, enabled=False)
        sent = _run(app, "/", [(b"host", b"127.0.0.1:8080")])
        self.assertEqual(sent[0]["status"], 200)

    def test_forwarded_proto_reads_first_value(self):
        scope = {
            "type": "http",
            "scheme": "http",
            "headers": [(b"x-forwarded-proto", b"https,http")],
        }
        self.assertEqual(forwarded_proto(scope), "https")

    def test_local_fastapi_does_not_install_loop(self):
        inner = FastAPI()

        @inner.get("/ping")
        def ping() -> dict:
            return {"ok": True}

        app = FastAPI()
        app.add_middleware(HttpsRedirectMiddleware, enabled=False)
        app.mount("/", inner)
        client = TestClient(app)
        response = client.get("/ping")
        self.assertEqual(response.status_code, 200)


class EnvSettingsTests(unittest.TestCase):
    def test_railway_environment_is_production(self):
        with patch.dict(os.environ, {"RAILWAY_ENVIRONMENT": "production"}, clear=False):
            os.environ.pop("ENV", None)
            row = Settings(_env_file=None)
        self.assertEqual(row.env, "production")
        self.assertTrue(row.cookie_secure)

    def test_explicit_env_production(self):
        with patch.dict(os.environ, {"ENV": "production"}, clear=False):
            row = Settings(_env_file=None)
        self.assertEqual(row.env, "production")


if __name__ == "__main__":
    unittest.main()
