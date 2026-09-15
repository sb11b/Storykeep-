from __future__ import annotations

import asyncio
import unittest

from app.http_limits import LimitChatBodyMiddleware


POLL_CAP = 50


async def _streaming_app(scope, receive, send) -> None:
    """Mimic StreamingResponse: poll receive() until the client disconnects."""
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"text/event-stream")],
        }
    )
    await send({"type": "http.response.body", "body": b"data: hi\n\n", "more_body": True})
    for _ in range(POLL_CAP):
        message = await receive()
        if message["type"] == "http.disconnect":
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return
    raise AssertionError("receive() never reported http.disconnect")


def _scope(body: bytes) -> dict:
    return {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
    }


class ChatBodyMiddlewareStreamTests(unittest.TestCase):
    """The body shim must not answer receive() forever once the body is replayed."""

    def _run(self, body: bytes) -> list[dict]:
        incoming = [
            {"type": "http.request", "body": body, "more_body": False},
            {"type": "http.disconnect"},
        ]
        sent: list[dict] = []

        async def receive() -> dict:
            if incoming:
                return incoming.pop(0)
            await asyncio.sleep(3600)
            raise AssertionError("unreachable")

        async def send(message: dict) -> None:
            sent.append(message)

        async def main() -> None:
            app = LimitChatBodyMiddleware(_streaming_app)
            await asyncio.wait_for(app(_scope(body), receive, send), timeout=2.0)

        asyncio.run(main())
        return sent

    def test_stream_finishes_instead_of_spinning_on_receive(self):
        sent = self._run(b'{"message": "hello"}')
        self.assertEqual(sent[0]["status"], 200)
        self.assertIn(b"data: hi", sent[1]["body"])
        self.assertFalse(sent[-1].get("more_body"))

    def test_oversized_body_is_rejected(self):
        body = b'{"message": "' + b"x" * 500_000 + b'"}'
        sent = self._run(body)
        self.assertEqual(sent[0]["status"], 413)


if __name__ == "__main__":
    unittest.main()
