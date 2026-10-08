from __future__ import annotations

import json
import logging
import re
import threading
import time
import traceback

from fastapi import HTTPException, Request, status
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import settings

logger = logging.getLogger(__name__)

# JSON body for POST /api/v1/chat. Larger than ChatIn.max_length so valid
# 100k-char messages still parse; anything huge is 413 before json.loads.
CHAT_BODY_MAX_BYTES = 420_000
CHAT_MESSAGE_MAX_CHARS = 100_000
CHAT_PATHS = frozenset({"/api/v1/chat"})
PAYLOAD_TOO_LARGE = "This turn is over the cap. Include a heading, a selection, or the next chunk."
PAYLOAD_THREAD_TOO_LARGE = "This thread slice is too long. Shorten your message or start a new chat."

_SECRET_RE = re.compile(
    r"(?i)(?:"
    r"xai-[A-Za-z0-9_-]{8,}|"
    r"fmu1-[A-Za-z0-9_-]+|"
    r"bearer\s+[A-Za-z0-9._\-+/=]+|"
    r"authorization:\s*\S+|"
    r"sk_access=[^;\s]+|"
    r"cookie:\s*\S+"
    r")"
)


def redact_secrets(text: str | None) -> str:
    return _SECRET_RE.sub("[redacted]", text or "")


def log_chat_exception(context: str, **extra: object) -> None:
    """Log type + traceback with API keys stripped. Never dump the chat body."""
    tb = redact_secrets(traceback.format_exc())
    bits = " ".join(f"{key}={value}" for key, value in extra.items() if value is not None)
    logger.error("%s %s\n%s", context, bits, tb)


def log_model_call(
    *,
    user_id: object | None = None,
    chat_id: object | None = None,
    message_id: object | None = None,
    slice_id: str | None = None,
    n_chars: int = 0,
    status: object | None = None,
) -> None:
    """Structured metadata for xAI turns. Never log message bodies or prompts."""
    logger.info(
        "model_call user_id=%s chat_id=%s message_id=%s slice=%s n_chars=%s status=%s",
        user_id or "-",
        chat_id or "-",
        message_id or "-",
        slice_id or "-",
        n_chars,
        status or "-",
    )


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


def payload_too_large_body(detail: str | None = None) -> bytes:
    message = detail or PAYLOAD_TOO_LARGE
    return (
        b'{"detail":"'
        + message.replace('"', '\\"').encode()
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
                await _send_json(send, 413, payload_too_large_body(PAYLOAD_THREAD_TOO_LARGE))
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


# ---------------------------------------------------------------------------
# IP-based login rate limiting (in-memory, single-process).
# 10 attempts per minute per client IP. Returns 429 on exceed.
# ---------------------------------------------------------------------------

LOGIN_RATE_MAX_ATTEMPTS = 10
LOGIN_RATE_WINDOW_SECONDS = 60

_login_attempts: dict[str, list[float]] = {}
_login_lock = threading.Lock()
_last_login_sweep = 0.0


def _prune_login_attempts(now: float) -> None:
    """Drop empty/stale buckets so the dict cannot grow without bound.

    Called under ``_login_lock`` at most once per window. Buckets whose newest
    hit is older than the window are removed; that also keeps per-IP entries
    from lingering after an attacker stops.
    """
    global _last_login_sweep
    if now - _last_login_sweep < LOGIN_RATE_WINDOW_SECONDS:
        return
    _last_login_sweep = now
    cutoff = now - LOGIN_RATE_WINDOW_SECONDS
    stale = [key for key, hits in _login_attempts.items() if not hits or hits[-1] <= cutoff]
    for key in stale:
        del _login_attempts[key]


def _trusted_proxies() -> frozenset[str]:
    raw = getattr(settings, "trusted_proxies", "") or ""
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _client_ip(request: Request) -> str:
    """Client IP for rate limiting.

    X-Forwarded-For is honored ONLY when the direct peer is a configured
    trusted proxy; otherwise it is attacker-controlled and would let a caller
    pick a new bucket per request (bypassing the limit). Untrusted peers are
    keyed by their socket address.
    """
    peer = request.client.host if request.client else "unknown"
    trusted = _trusted_proxies()
    if peer in trusted:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Right-most entry is the one appended by the nearest trusted proxy;
            # the left-most is client-supplied and spoofable.
            candidate = forwarded.split(",")[-1].strip()
            if candidate:
                return candidate
    return peer


def _login_rate_key(request: Request, email: str | None = None) -> str:
    """Rate-limit key: per IP, and additionally per (IP, account).

    A single IP is the blunt instrument; an attacker spread across many IPs can
    still hammer one account, so callers that already know the account pass the
    lowercased email and get a second, narrower bucket.
    """
    ip = _client_ip(request)
    if email:
        return f"{ip}|{email.strip().lower()}"
    return ip


def _consume_login_attempt(key: str) -> None:
    now = time.monotonic()
    cutoff = now - LOGIN_RATE_WINDOW_SECONDS
    with _login_lock:
        _prune_login_attempts(now)
        hits = [t for t in _login_attempts.get(key, []) if t > cutoff]
        if len(hits) >= LOGIN_RATE_MAX_ATTEMPTS:
            _login_attempts[key] = hits
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Please try again in a minute.",
                headers={"Retry-After": str(LOGIN_RATE_WINDOW_SECONDS)},
            )
        hits.append(now)
        _login_attempts[key] = hits


def check_login_rate_limit(request: Request) -> None:
    """FastAPI dependency: raise 429 if the login IP exceeded the rate limit."""
    _consume_login_attempt(_login_rate_key(request))


# Account-wide limit: bounds attempts against one account across ALL source
# IPs. The per-(IP, account) bucket above only covers one source, so eleven
# requests from eleven IPs would slip under it. This ceiling is deliberately
# looser than the per-IP limit so ordinary retries are not punished.
LOGIN_EMAIL_MAX_ATTEMPTS = 30
_login_email_attempts: dict[str, list[float]] = {}


def _consume_email_attempt(email: str) -> None:
    now = time.monotonic()
    cutoff = now - LOGIN_RATE_WINDOW_SECONDS
    key = email.strip().lower()
    with _login_lock:
        hits = [t for t in _login_email_attempts.get(key, []) if t > cutoff]
        if len(hits) >= LOGIN_EMAIL_MAX_ATTEMPTS:
            _login_email_attempts[key] = hits
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts for this account. Please try again in a minute.",
                headers={"Retry-After": str(LOGIN_RATE_WINDOW_SECONDS)},
            )
        hits.append(now)
        _login_email_attempts[key] = hits
        if now - _last_login_sweep >= LOGIN_RATE_WINDOW_SECONDS:
            stale = [k for k, v in _login_email_attempts.items() if not v or v[-1] <= cutoff]
            for k in stale:
                del _login_email_attempts[k]


def check_login_email_rate_limit(request: Request, email: str) -> None:
    """Account-scoped limiters. Call from the login handler once the submitted
    email is known, before the password lookup. Applies both a per-(IP,
    account) bucket and an account-wide bucket across all IPs."""
    _consume_login_attempt(_login_rate_key(request, email))
    _consume_email_attempt(email)
