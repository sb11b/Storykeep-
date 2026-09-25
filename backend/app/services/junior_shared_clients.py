"""Callers for the Junior phone app and the Windows overlay.

Both use the existing `/api/v1/junior/*` routes. There is no phone-only or
overlay-only URL. `venue` and `device_label` are what mark the client.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

PHONE_VENUE = "phone"
WINDOWS_VENUE = "windows"
PHONE_PROJECT = "junior-phone"
WINDOWS_PROJECT = "windows-overlay"
PHONE_DEVICE = "junior-mobile"
WINDOWS_DEVICE = "windows-overlay"

API_PREFIX = "/api/v1/junior"


class SharedMemoryClient:
    def __init__(self, http: Any, *, venue: str, project_slug: str, device_label: str) -> None:
        self.http = http
        self.venue = venue
        self.project_slug = project_slug
        self.device_label = device_label

    def open_thread(self, title: str, *, text: str | None = None) -> Any:
        body: dict[str, Any] = {
            "title": title,
            "venue": self.venue,
            "device_label": self.device_label,
        }
        if text:
            body["text"] = text
        return self.http.post(f"{API_PREFIX}/threads", json=body)

    def post_turn(self, text: str, *, thread_id: UUID | str | None = None) -> Any:
        body: dict[str, Any] = {
            "text": text,
            "venue": self.venue,
            "device_label": self.device_label,
        }
        if thread_id is None:
            return self.http.post(f"{API_PREFIX}/messages", json=body)
        return self.http.post(f"{API_PREFIX}/threads/{thread_id}/messages", json=body)

    def search(self, query: str) -> Any:
        return self.http.get(f"{API_PREFIX}/search", params={"q": query})

    def project(self) -> Any:
        return self.http.get(f"{API_PREFIX}/projects/{self.project_slug}")


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
