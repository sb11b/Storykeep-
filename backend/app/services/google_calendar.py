from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import GoogleCalendarAccount
from app.services.crypto_box import decrypt_secret, encrypt_secret
from app.services.google_oauth import (
    CALENDAR_EVENTS_SCOPE,
    fetch_userinfo,
    refresh_access_token,
    revoke_token,
)

EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


def is_connected(db: Session, user_id: UUID) -> bool:
    row = db.get(GoogleCalendarAccount, user_id)
    return bool(row and row.access_token_encrypted)


def status_payload(db: Session, user_id: UUID, *, configured: bool, demo_locked: bool) -> dict[str, object]:
    row = db.get(GoogleCalendarAccount, user_id)
    return {
        "configured": configured,
        "connected": bool(row and row.access_token_encrypted) and not demo_locked,
        "google_email": row.google_email if row and not demo_locked else None,
        "demo_locked": demo_locked,
    }


def store_tokens(
    db: Session,
    user_id: UUID,
    *,
    access_token: str,
    refresh_token: str | None,
    expiry: datetime,
    scope: str,
    google_sub: str | None,
    google_email: str | None,
) -> GoogleCalendarAccount:
    row = db.get(GoogleCalendarAccount, user_id)
    if row is None:
        row = GoogleCalendarAccount(user_id=user_id, access_token_encrypted="", scope=scope)
        db.add(row)
    row.access_token_encrypted = encrypt_secret(access_token)
    if refresh_token:
        row.refresh_token_encrypted = encrypt_secret(refresh_token)
    elif not row.refresh_token_encrypted:
        row.refresh_token_encrypted = None
    row.token_expiry = expiry
    row.scope = scope or CALENDAR_EVENTS_SCOPE
    row.google_sub = google_sub
    row.google_email = google_email
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return row


def disconnect(db: Session, user_id: UUID) -> None:
    row = db.get(GoogleCalendarAccount, user_id)
    if not row:
        return
    access = decrypt_secret(row.access_token_encrypted)
    refresh = decrypt_secret(row.refresh_token_encrypted) if row.refresh_token_encrypted else None
    revoke_token(access)
    revoke_token(refresh)
    db.delete(row)
    db.flush()


def _access_token(db: Session, user_id: UUID) -> str:
    row = db.get(GoogleCalendarAccount, user_id)
    if not row:
        raise HTTPException(status_code=409, detail="Connect Google Calendar first.")
    access = decrypt_secret(row.access_token_encrypted)
    if not access:
        raise HTTPException(status_code=409, detail="Connect Google Calendar first.")
    now = datetime.now(timezone.utc)
    expiry = row.token_expiry
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry and expiry > now + timedelta(seconds=30):
        return access
    refresh = decrypt_secret(row.refresh_token_encrypted) if row.refresh_token_encrypted else None
    if not refresh:
        raise HTTPException(status_code=401, detail="Google Calendar needs to be connected again.")
    refreshed = refresh_access_token(refresh)
    row.access_token_encrypted = encrypt_secret(str(refreshed["access_token"]))
    row.token_expiry = refreshed["expiry"]  # type: ignore[assignment]
    row.scope = str(refreshed.get("scope") or row.scope)
    row.updated_at = now
    db.flush()
    return str(refreshed["access_token"])


def remember_profile(db: Session, user_id: UUID, access_token: str) -> None:
    info = fetch_userinfo(access_token)
    row = db.get(GoogleCalendarAccount, user_id)
    if not row:
        return
    if info.get("sub"):
        row.google_sub = str(info["sub"])
    if info.get("email"):
        row.google_email = str(info["email"])


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _raise_google(response: httpx.Response) -> None:
    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Google Calendar needs to be connected again.")
    if response.status_code == 403:
        raise HTTPException(status_code=403, detail="Google Calendar denied that request.")
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="That event is gone.")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Google Calendar request failed.")


def _event_out(item: dict) -> dict[str, object]:
    start = item.get("start") or {}
    end = item.get("end") or {}
    return {
        "id": item.get("id"),
        "title": item.get("summary") or "(No title)",
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "all_day": bool(start.get("date") and not start.get("dateTime")),
        "html_link": item.get("htmlLink"),
        "updated": item.get("updated"),
    }


def list_events(db: Session, user_id: UUID, *, time_min: str, time_max: str, timezone_name: str) -> list[dict[str, object]]:
    token = _access_token(db, user_id)
    params = {
        "timeMin": time_min,
        "timeMax": time_max,
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "250",
        "timeZone": timezone_name,
    }
    with httpx.Client(timeout=25.0) as client:
        response = client.get(EVENTS_URL, headers=_headers(token), params=params)
    if response.status_code >= 400:
        _raise_google(response)
    items = response.json().get("items") or []
    return [_event_out(item) for item in items if isinstance(item, dict)]


def create_event(
    db: Session,
    user_id: UUID,
    *,
    title: str,
    start: str,
    end: str,
    timezone_name: str,
) -> dict[str, object]:
    token = _access_token(db, user_id)
    body = {
        "summary": title.strip(),
        "start": {"dateTime": start, "timeZone": timezone_name},
        "end": {"dateTime": end, "timeZone": timezone_name},
    }
    with httpx.Client(timeout=20.0) as client:
        response = client.post(EVENTS_URL, headers=_headers(token), json=body)
    if response.status_code >= 400:
        _raise_google(response)
    return _event_out(response.json())


def patch_event(
    db: Session,
    user_id: UUID,
    event_id: str,
    *,
    title: str | None,
    start: str | None,
    end: str | None,
    timezone_name: str,
) -> dict[str, object]:
    token = _access_token(db, user_id)
    body: dict[str, object] = {}
    if title is not None:
        body["summary"] = title.strip()
    if start:
        body["start"] = {"dateTime": start, "timeZone": timezone_name}
    if end:
        body["end"] = {"dateTime": end, "timeZone": timezone_name}
    url = f"{EVENTS_URL}/{event_id}"
    with httpx.Client(timeout=20.0) as client:
        response = client.patch(url, headers=_headers(token), json=body)
    if response.status_code >= 400:
        _raise_google(response)
    return _event_out(response.json())


def delete_event(db: Session, user_id: UUID, event_id: str) -> None:
    token = _access_token(db, user_id)
    url = f"{EVENTS_URL}/{event_id}"
    with httpx.Client(timeout=20.0) as client:
        response = client.delete(url, headers=_headers(token))
    if response.status_code not in {204, 200, 410}:
        _raise_google(response)
