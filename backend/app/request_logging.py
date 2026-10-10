from __future__ import annotations

import logging
import time
from typing import Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.auth import decode_access_token

logger = logging.getLogger(__name__)

JUNIOR_LOG_PREFIXES = (
    "/api/v1/chat",
    "/api/v1/junior",
    "/api/v1/stt",
    "/api/v1/search",
    "/api/v1/school",
)


def _header_map(scope: Scope) -> dict[str, str]:
    return {
        key.decode("latin1").lower(): value.decode("latin1")
        for key, value in scope.get("headers") or []
    }


def _user_id_from_scope(scope: Scope) -> str | None:
    """Resolve user id from the session cookie without logging the token."""
    cookie = _header_map(scope).get("cookie") or ""
    token = None
    for part in cookie.split(";"):
        bit = part.strip()
        if bit.startswith("sk_access="):
            token = bit.split("=", 1)[1].strip()
            break
    if not token:
        return None
    try:
        return str(decode_access_token(token))
    except Exception:
        return None


class JuniorRequestLogMiddleware:
    """Log Junior API metadata only — never bodies, cookies, or Authorization."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = (scope.get("path") or "").rstrip("/") or "/"
        if not any(path.startswith(prefix) for prefix in JUNIOR_LOG_PREFIXES):
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code = 500
        user_id = _user_id_from_scope(scope)
        headers = scope.get("headers") or []
        auth_header = ""
        for key, value in headers:
            if key.lower() == b"authorization":
                auth_header = value.decode("latin-1", errors="replace")
                break
        has_access_cookie = False
        for key, value in headers:
            if key.lower() != b"cookie":
                continue
            cookie = value.decode("latin-1", errors="replace")
            for part in cookie.split(";"):
                name, _, val = part.strip().partition("=")
                # Name must be exactly sk_access with a NON-EMPTY value —
                # matches deps.py, where sk_access="" is falsy and 401s.
                if name == "sk_access" and val:
                    has_access_cookie = True
                    break
            if has_access_cookie:
                break
        # Bearer scheme is case-insensitive (RFC 7235) and deps.py matches it
        # case-insensitively — the tag must reflect actual auth state.
        if auth_header.lower().startswith("bearer "):
            auth = "auth=bearer"
        elif has_access_cookie:
            auth = "auth=cookie"
        else:
            auth = "auth=none"

        async def tracked_send(message: Message) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status") or 500)
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        finally:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "junior_request path=%s method=%s user_id=%s %s status=%s latency_ms=%s",
                path,
                (scope.get("method") or "").upper(),
                user_id or "-",
                auth,
                status_code,
                latency_ms,
            )
