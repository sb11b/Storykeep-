from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services import fastmail_calendar as fmcal


def is_connected(db: Session, user_id: UUID) -> bool:
    return fmcal.is_connected(db, user_id)


def status_payload(db: Session, user_id: UUID, *, demo_locked: bool) -> dict[str, object]:
    fastmail = fmcal.status_payload(db, user_id, demo_locked=demo_locked)
    connected = bool(fastmail.get("connected"))
    return {
        "configured": True,
        "fastmail_configured": True,
        "connected": connected,
        "provider": "fastmail" if connected else None,
        "fastmail_email": fastmail.get("fastmail_email"),
        "calendar_name": fastmail.get("calendar_name"),
        "calendars": fastmail.get("calendars") or [],
        "demo_locked": demo_locked,
    }


def list_events(db: Session, user_id: UUID, *, time_min: str, time_max: str, timezone_name: str) -> list[dict[str, object]]:
    del timezone_name
    if not fmcal.is_connected(db, user_id):
        raise HTTPException(status_code=409, detail="Connect Fastmail Calendar first.")
    return fmcal.list_events(db, user_id, time_min=time_min, time_max=time_max)


def create_event(
    db: Session,
    user_id: UUID,
    *,
    title: str,
    start: str,
    end: str,
    timezone_name: str,
    location: str | None = None,
    meeting_url: str | None = None,
    online: bool = False,
    color: str | None = None,
    calendar_id: str | None = None,
) -> dict[str, object]:
    del timezone_name
    if not fmcal.is_connected(db, user_id):
        raise HTTPException(status_code=409, detail="Connect Fastmail Calendar first.")
    return fmcal.create_event(
        db,
        user_id,
        title=title,
        start=start,
        end=end,
        location=location,
        meeting_url=meeting_url,
        online=online,
        color=color,
        calendar_id=calendar_id,
    )


def patch_event(
    db: Session,
    user_id: UUID,
    event_id: str,
    *,
    title: str | None,
    start: str | None,
    end: str | None,
    timezone_name: str,
    location: str | None = None,
    meeting_url: str | None = None,
    online: bool | None = None,
    color: str | None = None,
    calendar_id: str | None = None,
) -> dict[str, object]:
    del timezone_name
    return fmcal.patch_event(
        db,
        user_id,
        event_id,
        title=title,
        start=start,
        end=end,
        location=location,
        meeting_url=meeting_url,
        online=online,
        color=color,
        calendar_id=calendar_id,
    )


def delete_event(db: Session, user_id: UUID, event_id: str) -> None:
    fmcal.delete_event(db, user_id, event_id)


def disconnect(db: Session, user_id: UUID) -> None:
    fmcal.disconnect(db, user_id)
