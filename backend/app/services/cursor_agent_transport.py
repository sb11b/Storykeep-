"""Owns the Cursor Cloud Agent HTTP transport layer (auth, repo resolution, request helpers) extracted from cursor_agent_tool."""

from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.config import settings
from app.services.demo_lock import is_locked

TIMEOUT_SEC = 45.0


def _api_key() -> str:
    return (settings.cursor_api_key or "").strip()


def _analytics_key() -> str:
    return (settings.cursor_analytics_key or settings.cursor_api_key or "").strip()


def _repo_slug() -> str:
    override = (settings.cursor_agent_repo or "").strip().strip("/")
    if override:
        return override
    return (settings.github_repo or "sb11b/Storykeep-").strip().strip("/")


def _repo_url() -> str:
    slug = _repo_slug()
    if slug.startswith("http://") or slug.startswith("https://"):
        return slug.rstrip("/")
    return f"https://github.com/{slug}"


def configured() -> bool:
    return bool(_api_key())


def owner_can_use(user: object | None) -> bool:
    return configured() and not is_locked(user)


def reject_demo(user: object) -> None:
    if is_locked(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cursor Cloud Agent is not enabled on this account",
        )


def _api_root() -> str:
    return (settings.cursor_api_url or "https://api.cursor.com").rstrip("/")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    key = _api_key()
    if not key:
        return 503, {"message": "Cursor API key not configured"}
    url = f"{_api_root()}{path}"
    try:
        with httpx.Client(timeout=TIMEOUT_SEC) as client:
            response = client.request(method, url, headers=_headers(), json=payload)
    except httpx.TimeoutException:
        return 504, {"message": "Cursor API timeout"}
    except httpx.HTTPError as exc:
        return 502, {"message": f"Cursor transport error: {exc}"}
    try:
        body = response.json()
    except json.JSONDecodeError:
        body = {"message": response.text[:500]}
    return response.status_code, body


def _post(path: str, payload: dict[str, Any]) -> tuple[int, Any]:
    return _request("POST", path, payload)


def _get(path: str) -> tuple[int, Any]:
    return _request("GET", path)


def _analytics_get(path: str, params: dict[str, str]) -> tuple[int, Any]:
    """Analytics uses HTTP basic auth. The Cloud Agent calls keep using a bearer token."""
    key = _analytics_key()
    if not key:
        return 503, {"message": "Cursor API key not configured"}
    url = f"{_api_root()}{path}"
    try:
        with httpx.Client(timeout=TIMEOUT_SEC) as client:
            response = client.get(url, params=params, auth=(key, ""))
    except httpx.TimeoutException:
        return 504, {"message": "Cursor API timeout"}
    except httpx.HTTPError as exc:
        return 502, {"message": f"Cursor transport error: {exc}"}
    try:
        body = response.json()
    except json.JSONDecodeError:
        body = {"message": response.text[:500]}
    return response.status_code, body
