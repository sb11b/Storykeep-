from __future__ import annotations

import json
import logging
import re
import traceback

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# JSON body for POST /api/v1/chat. Larger than ChatIn.max_length so valid
# 100k-char messages still parse; anything huge is 413 before json.loads.
CHAT_BODY_MAX_BYTES = 420_000
CHAT_MESSAGE_MAX_CHARS = 100_000
CHAT_PATHS = frozenset({"/api/v1/chat"})
PAYLOAD_TOO_LARGE = "This turn is over the cap. Include a heading, a selection, or the next chunk."

_SECRET_RE = re.compile(
    r"(?i)(?:xai-[A-Za-z0-9_-]{8,}|bearer\s+[A-Za-z0-9._\-+/=]+|authorization:\s*\S+)"
)


def redact_secrets(text: str | None) -> str:
    return _SECRET_RE.sub("[redacted]", text or "")


def log_chat_exception(context: str, **extra: object) -> None:
    """Log type + traceback with API keys stripped. Never dump the chat body."""
    tb = redact_secrets(traceback.format_exc())
    bits = " ".join(f"{key}={value}" for key, value in extra.items() if value is not None)
    logger.error("%s %s\n%s", context, bits, tb)


def _is_chat_post(scope: Scope) -> bool:
    if scope.get("type") != "http":
        return False
    if (scope.get("method") or "").upper() != "POST":
        return False
    path = (scope.get("path") or "").rstrip("/") or "/"
    return path in CHAT_PATHS


async def _send_json(send: Send, status: int, body: bytes) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def payload_too_large_body() -> bytes:
    return (
        b'{"detail":"'
        + PAYLOAD_TOO_LARGE.replace('"', '\\"').encode()
        + b'","code":"payload_too_large"}'
    )


class LimitChatBodyMiddleware:
    """Reject oversized /chat bodies before JSON parse so the worker stays up."""

    def __init__(self, app: ASGIApp, max_bytes: int = CHAT_BODY_MAX_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not _is_chat_post(scope):
            await self.app(scope, receive, send)
            return
        headers = {key.decode("latin1").lower(): value.decode("latin1") for key, value in scope.get("headers") or []}
        raw_length = headers.get("content-length") or ""
        try:
            announced = int(raw_length) if raw_length else 0
        except ValueError:
            announced = 0
        if announced > self.max_bytes:
            logger.error("chat body rejected content-length=%s max=%s", announced, self.max_bytes)
            await _send_json(send, 413, payload_too_large_body())
            return

        chunks: list[bytes] = []
        total = 0
        more = True
        try:
            while more:
                message = await receive()
                mtype = message.get("type")
                if mtype == "http.disconnect":
                    return
                if mtype != "http.request":
                    continue
                piece = message.get("body") or b""
                total += len(piece)
                if total > self.max_bytes:
                    logger.error("chat body rejected bytes=%s max=%s", total, self.max_bytes)
                    while message.get("more_body"):
                        message = await receive()
                        if message.get("type") == "http.disconnect":
                            return
                    await _send_json(send, 413, payload_too_large_body())
                    return
                chunks.append(piece)
                more = bool(message.get("more_body"))
        except MemoryError:
            log_chat_exception("chat body memory error")
            await _send_json(send, 413, payload_too_large_body())
            return

        buffered = b"".join(chunks)
        try:
            parsed = json.loads(buffered) if buffered else None
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            msg = parsed.get("message")
            if isinstance(msg, str) and len(msg) > CHAT_MESSAGE_MAX_CHARS:
                logger.error(
                    "chat message rejected chars=%s max=%s",
                    len(msg),
                    CHAT_MESSAGE_MAX_CHARS,
                )
                await _send_json(send, 413, payload_too_large_body())
                return

        sent = False
        started = False

        async def replay() -> dict:
            nonlocal sent
            if sent:
                # StreamingResponse polls receive() until http.disconnect. Answering
                # that with a synthetic message spins the loop with no await, which
                # pegs the GIL and freezes the worker. Wait on the real client.
                return await receive()
            sent = True
            return {"type": "http.request", "body": buffered, "more_body": False}

        async def tracked_send(message: dict) -> None:
            nonlocal started
            if message.get("type") == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, replay, tracked_send)
        except MemoryError:
            log_chat_exception("chat handler memory error")
            if not started:
                await _send_json(send, 413, payload_too_large_body())
        except Exception:
            log_chat_exception("chat handler crashed")
            if not started:
                await _send_json(send, 500, b'{"detail":"Chat failed."}')
