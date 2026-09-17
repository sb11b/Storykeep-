from __future__ import annotations

from starlette.datastructures import URL
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

HEALTH_PATHS = frozenset({"/health", "/api/health"})


def header_value(scope: Scope, name: bytes) -> str:
    target = name.lower()
    for key, value in scope.get("headers") or []:
        if key == target:
            return value.decode("latin-1").strip()
    return ""


def forwarded_proto(scope: Scope) -> str:
    raw = header_value(scope, b"x-forwarded-proto")
    if raw:
        first = raw.split(",", 1)[0].strip().lower()
        if first in {"https", "wss"}:
            return "https"
        if first in {"http", "ws"}:
            return "http"
    if header_value(scope, b"x-forwarded-ssl").lower() == "on":
        return "https"
    return (scope.get("scheme") or "http").lower()


def public_host(scope: Scope) -> str:
    forwarded = header_value(scope, b"x-forwarded-host")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return header_value(scope, b"host")


class HttpsRedirectMiddleware:
    """Production only: trust Railway X-Forwarded-Proto, redirect remaining http."""

    def __init__(self, app: ASGIApp, *, enabled: bool) -> None:
        self.app = app
        self.enabled = enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.enabled or scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        if path in HEALTH_PATHS:
            await self.app(scope, receive, send)
            return
        proto = forwarded_proto(scope)
        if proto == "https":
            if scope.get("scheme") != "https":
                scope = dict(scope)
                scope["scheme"] = "https"
            await self.app(scope, receive, send)
            return
        host = public_host(scope)
        if not host:
            await self.app(scope, receive, send)
            return
        url = URL(scope=scope).replace(scheme="https", netloc=host)
        response = RedirectResponse(str(url), status_code=308)
        await response(scope, receive, send)
