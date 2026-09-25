"""Callers for the Junior phone app and the Windows overlay.

Both use the existing `/api/v1/junior/*` routes. There is no phone-only or
overlay-only URL. `venue` and `device_label` are what mark the client.

Writes retry on 401/403/5xx and keep a visible error plus the last unsaved
post so a failed turn is never dropped silently.
"""

from __future__ import annotations

import time
from typing import Any, Callable
from uuid import UUID

PHONE_VENUE = "phone"
WINDOWS_VENUE = "windows"
PHONE_PROJECT = "junior-phone"
WINDOWS_PROJECT = "windows-overlay"
PHONE_DEVICE = "junior-mobile"
WINDOWS_DEVICE = "windows-overlay"

API_PREFIX = "/api/v1/junior"
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (0.25, 0.5)
RETRY_STATUSES = frozenset({401, 403, *range(500, 600)})

ERROR_SIGN_IN = "Sign in to use Junior shared memory."
ERROR_FORBIDDEN = "This account cannot use Junior shared memory."
ERROR_SERVER = "Junior could not complete that request. Try again."
ERROR_NETWORK = "Junior could not reach shared memory. Try again."
ERROR_POST_DROPPED = "Junior could not save that message. It was not dropped — tap retry."


class SharedMemoryResult:
    """HTTP-shaped result with a user-visible error when the call failed."""

    def __init__(
        self,
        response: Any | None,
        *,
        error: str | None = None,
        attempts: int = 1,
        payload: dict[str, Any] | None = None,
        method: str = "GET",
        path: str = "",
    ) -> None:
        self.response = response
        self.status_code = int(getattr(response, "status_code", 0) or 0)
        self.attempts = attempts
        self.payload = payload
        self.method = method
        self.path = path
        self.error = error

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status_code < 300

    def __bool__(self) -> bool:
        return self.ok

    def json(self) -> Any:
        if self.response is None:
            return {"detail": self.error, "status_code": self.status_code}
        return self.response.json()

    @property
    def text(self) -> str:
        if self.response is None:
            return self.error or ""
        return str(getattr(self.response, "text", "") or "")


class SharedMemoryClient:
    def __init__(
        self,
        http: Any,
        *,
        venue: str,
        project_slug: str,
        device_label: str,
        sleeper: Callable[[float], None] | None = None,
        max_attempts: int = MAX_ATTEMPTS,
    ) -> None:
        self.http = http
        self.venue = venue
        self.project_slug = project_slug
        self.device_label = device_label
        self._sleep = sleeper or time.sleep
        self.max_attempts = max(1, int(max_attempts))
        self.last_error: str | None = None
        self.last_failed_post: dict[str, Any] | None = None

    def open_thread(self, title: str, *, text: str | None = None) -> SharedMemoryResult:
        body: dict[str, Any] = {
            "title": title,
            "venue": self.venue,
            "device_label": self.device_label,
        }
        if text:
            body["text"] = text
        return self._request("POST", f"{API_PREFIX}/threads", json=body, write=True)

    def post_turn(self, text: str, *, thread_id: UUID | str | None = None) -> SharedMemoryResult:
        body: dict[str, Any] = {
            "text": text,
            "venue": self.venue,
            "device_label": self.device_label,
        }
        if thread_id is None:
            path = f"{API_PREFIX}/messages"
        else:
            path = f"{API_PREFIX}/threads/{thread_id}/messages"
        return self._request("POST", path, json=body, write=True)

    def list_threads(self) -> SharedMemoryResult:
        return self._request("GET", f"{API_PREFIX}/threads")

    def list_messages(self, thread_id: UUID | str | None = None) -> SharedMemoryResult:
        if thread_id is None:
            return self._request("GET", f"{API_PREFIX}/messages")
        return self._request("GET", f"{API_PREFIX}/threads/{thread_id}/messages")

    def search(self, query: str) -> SharedMemoryResult:
        return self._request("GET", f"{API_PREFIX}/search", params={"q": query})

    def project(self) -> SharedMemoryResult:
        return self._request("GET", f"{API_PREFIX}/projects/{self.project_slug}")

    def _request(self, method: str, path: str, *, write: bool = False, **kwargs: Any) -> SharedMemoryResult:
        last: SharedMemoryResult | None = None
        verb = method.lower()
        caller = getattr(self.http, verb)
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = caller(path, **kwargs)
            except Exception:
                last = SharedMemoryResult(
                    None,
                    error=ERROR_NETWORK if not write else ERROR_POST_DROPPED,
                    attempts=attempt,
                    payload=kwargs.get("json"),
                    method=method,
                    path=path,
                )
            else:
                status = int(getattr(response, "status_code", 0) or 0)
                error = None if 200 <= status < 300 else _visible_error(status, write=write)
                last = SharedMemoryResult(
                    response,
                    error=error,
                    attempts=attempt,
                    payload=kwargs.get("json"),
                    method=method,
                    path=path,
                )
                if last.ok:
                    self.last_error = None
                    return last
                if status not in RETRY_STATUSES or attempt >= self.max_attempts:
                    break
            if attempt < self.max_attempts:
                delay = BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)]
                self._sleep(delay)
        assert last is not None
        self.last_error = last.error
        if write:
            self.last_failed_post = {
                "path": path,
                "payload": kwargs.get("json"),
                "error": last.error,
                "status_code": last.status_code,
                "attempts": last.attempts,
            }
        return last


def _visible_error(status_code: int, *, write: bool) -> str:
    if status_code == 401:
        return ERROR_SIGN_IN
    if status_code == 403:
        return ERROR_FORBIDDEN
    if write:
        return ERROR_POST_DROPPED
    return ERROR_SERVER


def phone_client(http: Any, **kwargs: Any) -> SharedMemoryClient:
    return SharedMemoryClient(
        http,
        venue=PHONE_VENUE,
        project_slug=PHONE_PROJECT,
        device_label=PHONE_DEVICE,
        **kwargs,
    )


def windows_client(http: Any, **kwargs: Any) -> SharedMemoryClient:
    return SharedMemoryClient(
        http,
        venue=WINDOWS_VENUE,
        project_slug=WINDOWS_PROJECT,
        device_label=WINDOWS_DEVICE,
        **kwargs,
    )
