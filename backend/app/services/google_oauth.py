from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID

import httpx
import jwt
from fastapi import HTTPException, status

from app.config import settings

CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo"


def google_configured() -> bool:
    return settings.google_calendar_configured


def assert_calendar_scope_only(scope: str) -> None:
    parts = [part.strip() for part in (scope or "").split() if part.strip()]
    if not parts:
        raise HTTPException(status_code=400, detail="Google Calendar did not return a calendar scope.")
    for part in parts:
        lowered = part.lower()
        if "gmail" in lowered or "imap" in lowered or "mail.google" in lowered:
            raise HTTPException(status_code=400, detail="Gmail access is not allowed.")
        if "calendar" not in lowered:
            raise HTTPException(status_code=400, detail="Only Google Calendar access is allowed.")


def public_origin(request_url: str, forwarded_proto: str | None, forwarded_host: str | None, host: str | None) -> str:
    override = (settings.google_oauth_redirect or "").strip()
    if override:
        return override.rstrip("/")
    proto = (forwarded_proto or "").split(",")[0].strip() or "https"
    hostname = (forwarded_host or host or "").split(",")[0].strip()
    if hostname:
        return f"{proto}://{hostname}".rstrip("/")
    return str(request_url).rstrip("/")


def callback_url(origin: str) -> str:
    return f"{origin.rstrip('/')}/api/v1/calendar/callback"


def encode_oauth_state(user_id: UUID) -> str:
    payload = {
        "sub": str(user_id),
        "purpose": "gcal",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.signing_key, algorithm="HS256")


def decode_oauth_state(token: str) -> UUID:
    try:
        payload = jwt.decode(token, settings.signing_key, algorithms=["HS256"])
        if payload.get("purpose") != "gcal":
            raise ValueError("purpose")
        return UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Google sign-in expired. Try Connect again.") from exc


def authorize_url(*, origin: str, state: str) -> str:
    if not google_configured():
        raise HTTPException(status_code=503, detail="Calendar is off until GOOGLE_CLIENT_ID is set on the server.")
    query = urlencode(
        {
            "client_id": settings.google_client_id.strip(),
            "redirect_uri": callback_url(origin),
            "response_type": "code",
            "scope": CALENDAR_EVENTS_SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "false",
            "state": state,
        }
    )
    return f"{GOOGLE_AUTH}?{query}"


def _token_headers() -> dict[str, str]:
    return {"Accept": "application/json"}


def exchange_code(code: str, origin: str) -> dict[str, object]:
    if not google_configured():
        raise HTTPException(status_code=503, detail="Calendar is off until GOOGLE_CLIENT_ID is set on the server.")
    data = {
        "code": code,
        "client_id": settings.google_client_id.strip(),
        "client_secret": settings.google_client_secret.strip(),
        "redirect_uri": callback_url(origin),
        "grant_type": "authorization_code",
    }
    with httpx.Client(timeout=20.0) as client:
        response = client.post(GOOGLE_TOKEN, data=data, headers=_token_headers())
    if response.status_code >= 400:
        raise HTTPException(status_code=400, detail="Google did not accept that sign-in. Try Connect again.")
    payload = response.json()
    scope = str(payload.get("scope") or CALENDAR_EVENTS_SCOPE)
    assert_calendar_scope_only(scope)
    access = str(payload.get("access_token") or "")
    if not access:
        raise HTTPException(status_code=400, detail="Google did not return a calendar token.")
    expires_in = int(payload.get("expires_in") or 3600)
    return {
        "access_token": access,
        "refresh_token": str(payload.get("refresh_token") or "") or None,
        "expiry": datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in - 60)),
        "scope": scope,
        "id_token": payload.get("id_token"),
    }


def refresh_access_token(refresh_token: str) -> dict[str, object]:
    data = {
        "refresh_token": refresh_token,
        "client_id": settings.google_client_id.strip(),
        "client_secret": settings.google_client_secret.strip(),
        "grant_type": "refresh_token",
    }
    with httpx.Client(timeout=20.0) as client:
        response = client.post(GOOGLE_TOKEN, data=data, headers=_token_headers())
    if response.status_code >= 400:
        raise HTTPException(status_code=401, detail="Google Calendar needs to be connected again.")
    payload = response.json()
    access = str(payload.get("access_token") or "")
    if not access:
        raise HTTPException(status_code=401, detail="Google Calendar needs to be connected again.")
    expires_in = int(payload.get("expires_in") or 3600)
    scope = str(payload.get("scope") or CALENDAR_EVENTS_SCOPE)
    assert_calendar_scope_only(scope)
    return {
        "access_token": access,
        "expiry": datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in - 60)),
        "scope": scope,
    }


def fetch_userinfo(access_token: str) -> dict[str, str | None]:
    with httpx.Client(timeout=15.0) as client:
        response = client.get(GOOGLE_USERINFO, headers={"Authorization": f"Bearer {access_token}"})
    if response.status_code >= 400:
        return {"sub": None, "email": None}
    payload = response.json()
    return {"sub": payload.get("sub"), "email": payload.get("email")}


def revoke_token(token: str | None) -> None:
    if not token:
        return
    try:
        with httpx.Client(timeout=10.0) as client:
            client.post(GOOGLE_REVOKE, params={"token": token})
    except httpx.HTTPError:
        pass
