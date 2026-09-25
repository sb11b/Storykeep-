"""Callers for the Junior phone app and the Windows overlay.

Both use the existing `/api/v1/junior/*` routes. There is no phone-only or
overlay-only URL. `venue` and `device_label` are what mark the client.

Writes retry on 401/403/5xx (and transport errors) with backoff. A failed
post never disappears: callers get a `SharedMemoryError` with a short
user-visible message after the last attempt.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

PHONE_VENUE = "phone"
WINDOWS_VENUE = "windows"
PHONE_PROJECT = "junior-phone"
WINDOWS_PROJECT = "windows-overlay"
PHONE_DEVICE = "junior-mobile"
WINDOWS_DEVICE = "windows-overlay"

API_PREFIX = "/api/v1/junior"

RETRY_STATUSES = frozenset({401, 403, 500, 502, 503, 504})
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (0.2, 0.5)


class SharedMemoryError(Exception):
    """Failed Memory API call after retries. `user_message` is safe to show."""

    def __init__(
        self,
        user_message: str,
        *,
        status_code: int | None = None,
        attempts: int = 1,
        action: str = "finish this request",
    ) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        self.status_code = status_code
        self.attempts = attempts
        self.action = action


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def user_visible_error(status_code: int | None, action: str) -> str:
    if status_code == 401:
        return f"Sign in required. Junior did not {action}."
    if status_code == 403:
        return f"This account cannot use Junior shared memory. Junior did not {action}."
    if status_code is not None and status_code >= 500:
        return f"Junior hit a server error and did not {action}. Try again."
    if status_code is None:
        return f"Junior could not reach the server and did not {action}."
    return f"Junior could not {action} (HTTP {status_code})."


def _status_code(response: Any) -> int | None:
    code = getattr(response, "status_code", None)
    if isinstance(code, int):
        return code
    return None


def _is_success(code: int | None) -> bool:
    return code is not None and 200 <= code < 300


class SharedMemoryClient:
    def __init__(self, http: Any, *, venue: str, project_slug: str, device_label: str) -> None:
        self.http = http
        self.venue = venue
        self.project_slug = project_slug
        self.device_label = device_label

    def _request(
        self,
        method: str,
        path: str,
        *,
        action: str,
        **kwargs: Any,
    ) -> Any:
        call = getattr(self.http, method)
        last_status: int | None = None
        last_exc: BaseException | None = None
        attempts = 0
        for attempt in range(1, MAX_ATTEMPTS + 1):
            attempts = attempt
            try:
                response = call(path, **kwargs)
            except SharedMemoryError:
                raise
            except Exception as exc:
                last_exc = exc
                last_status = None
                if attempt < MAX_ATTEMPTS:
                    _sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
                    continue
                raise SharedMemoryError(
                    user_visible_error(None, action),
                    status_code=None,
                    attempts=attempts,
                    action=action,
                ) from exc
            last_status = _status_code(response)
            if _is_success(last_status):
                return response
            if last_status in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                _sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
                continue
            raise SharedMemoryError(
                user_visible_error(last_status, action),
                status_code=last_status,
                attempts=attempts,
                action=action,
            )
        raise SharedMemoryError(
            user_visible_error(last_status, action),
            status_code=last_status,
            attempts=attempts,
            action=action,
        ) from last_exc

    def open_thread(self, title: str, *, text: str | None = None) -> Any:
        body: dict[str, Any] = {
            "title": title,
            "venue": self.venue,
            "device_label": self.device_label,
        }
        if text:
            body["text"] = text
        return self._request("post", f"{API_PREFIX}/threads", action="save this message", json=body)

    def post_turn(self, text: str, *, thread_id: UUID | str | None = None) -> Any:
        body: dict[str, Any] = {
            "text": text,
            "venue": self.venue,
            "device_label": self.device_label,
        }
        if thread_id is None:
            return self._request(
                "post",
                f"{API_PREFIX}/messages",
                action="save this message",
                json=body,
            )
        return self._request(
            "post",
            f"{API_PREFIX}/threads/{thread_id}/messages",
            action="save this message",
            json=body,
        )

    def get_threads(self) -> Any:
        return self._request("get", f"{API_PREFIX}/threads", action="load threads")

    def get_messages(self, thread_id: UUID | str) -> Any:
        return self._request(
            "get",
            f"{API_PREFIX}/threads/{thread_id}/messages",
            action="load messages",
        )

    def search(self, query: str) -> Any:
        return self._request("get", f"{API_PREFIX}/search", action="search", params={"q": query})

    def project(self) -> Any:
        return self._request(
            "get",
            f"{API_PREFIX}/projects/{self.project_slug}",
            action="load the project",
        )


def phone_client(http: Any) -> SharedMemoryClient:
    return SharedMemoryClient(
        http,
        venue=PHONE_VENUE,
        project_slug=PHONE_PROJECT,
        device_label=PHONE_DEVICE,
    )


def windows_client(http: Any) -> SharedMemoryClient:
    return SharedMemoryClient(
        http,
        venue=WINDOWS_VENUE,
        project_slug=WINDOWS_PROJECT,
        device_label=WINDOWS_DEVICE,
    )
