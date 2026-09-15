from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services import fastmail_calendar as fmcal
from app.services import google_calendar as gcal
from app.services import google_oauth


def provider_for(db: Session, user_id: UUID) -> str | None:
    if fmcal.is_connected(db, user_id):
        return "fastmail"
    if gcal.is_connected(db, user_id):
        return "google"
    return None


def is_connected(db: Session, user_id: UUID) -> bool:
    return provider_for(db, user_id) is not None


def status_payload(db: Session, user_id: UUID, *, demo_locked: bool) -> dict[str, object]:
    google = gcal.status_payload(
        db,
        user_id,
        configured=google_oauth.google_configured(),
        demo_locked=demo_locked,
    )
    fastmail = fmcal.status_payload(db, user_id, demo_locked=demo_locked)
    provider = None if demo_locked else provider_for(db, user_id)
    connected = bool(fastmail.get("connected") or google.get("connected"))
    return {
        "configured": True,
        "fastmail_configured": True,
        "google_configured": bool(google.get("configured")),
        "connected": connected,
        "provider": provider,
        "google_email": google.get("google_email"),
        "fastmail_email": fastmail.get("fastmail_email"),
        "calendar_name": fastmail.get("calendar_name"),
        "demo_locked": demo_locked,
    }


def list_events(db: Session, user_id: UUID, *, time_min: str, time_max: str, timezone_name: str) -> list[dict[str, object]]:
    kind = provider_for(db, user_id)
    if kind == "fastmail":
        return fmcal.list_events(db, user_id, time_min=time_min, time_max=time_max)
    if kind == "google":
        return gcal.list_events(db, user_id, time_min=time_min, time_max=time_max, timezone_name=timezone_name)
    raise HTTPException(status_code=409, detail="Connect Fastmail Calendar first.")


def create_event(
    db: Session,
    user_id: UUID,
    *,
    title: str,
    start: str,
    end: str,
    timezone_name: str,
) -> dict[str, object]:
    kind = provider_for(db, user_id)
    if kind == "fastmail":
        return fmcal.create_event(db, user_id, title=title, start=start, end=end)
    if kind == "google":
        return gcal.create_event(db, user_id, title=title, start=start, end=end, timezone_name=timezone_name)
    raise HTTPException(status_code=409, detail="Connect Fastmail Calendar first.")


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
    if event_id.startswith("fm-") or provider_for(db, user_id) == "fastmail":
        return fmcal.patch_event(db, user_id, event_id, title=title, start=start, end=end)
    return gcal.patch_event(
        db,
        user_id,
        event_id,
        title=title,
        start=start,
        end=end,
        timezone_name=timezone_name,
    )


def delete_event(db: Session, user_id: UUID, event_id: str) -> None:
    if event_id.startswith("fm-") or provider_for(db, user_id) == "fastmail":
        fmcal.delete_event(db, user_id, event_id)
        return
    gcal.delete_event(db, user_id, event_id)


def disconnect(db: Session, user_id: UUID) -> None:
    kind = provider_for(db, user_id)
    if kind == "fastmail":
        fmcal.disconnect(db, user_id)
        return
    gcal.disconnect(db, user_id)
