from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.services import calendar_access as calendars
from app.services import fastmail_calendar as fmcal
from app.services.calendar_tool import normalize_add_event
from app.services.nominatim_places import suggest_places
from app.services.demo_lock import is_locked, reject_locked

router = APIRouter(prefix="/calendar", tags=["calendar"])


class CalendarEventIn(BaseModel):
    title: str = Field(min_length=1, max_length=400)
    start: str
    end: str
    location: str | None = Field(default=None, max_length=400)
    meeting_url: str | None = Field(default=None, max_length=800)
    online: bool = False
    color: str | None = Field(default=None, max_length=16)
    calendar_id: str | None = Field(default=None, max_length=800)


class CalendarEventPatchIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=400)
    start: str | None = None
    end: str | None = None
    location: str | None = Field(default=None, max_length=400)
    meeting_url: str | None = Field(default=None, max_length=800)
    online: bool | None = None
    color: str | None = Field(default=None, max_length=16)
    calendar_id: str | None = Field(default=None, max_length=800)


class FastmailConnectIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    token: str = Field(min_length=8, max_length=400)
    calendar_url: str | None = Field(default=None, max_length=800)


def _tz(value: str | None) -> str:
    name = (value or "").strip() or "UTC"
    return name[:80]


@router.get("/status")
def calendar_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return calendars.status_payload(db, user.id, demo_locked=is_locked(user))


@router.post("/fastmail/connect")
def calendar_fastmail_connect(
    payload: FastmailConnectIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    row = fmcal.connect(db, user.id, email=payload.email, token=payload.token, calendar_url=payload.calendar_url)
    db.commit()
    return {
        "ok": True,
        "connected": True,
        "provider": "fastmail",
        "fastmail_email": row.fastmail_email,
        "calendar_name": row.calendar_name,
    }


@router.get("/places")
def calendar_places(
    q: str = Query(default="", max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    del db
    reject_locked(user)
    return {"items": suggest_places(q)}


@router.post("/disconnect")
def calendar_disconnect(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    reject_locked(user)
    calendars.disconnect(db, user.id)
    db.commit()
    return {"ok": True, "connected": False}


def _range(time_min: str | None, time_max: str | None, view: str) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    if time_min and time_max:
        return time_min, time_max
    if view == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start.isoformat(), end.isoformat()
    weekday = now.weekday()
    sunday = now - timedelta(days=(weekday + 1) % 7)
    start = sunday.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    return start.isoformat(), end.isoformat()


@router.get("/events")
def calendar_events(
    view: str = Query(default="week"),
    time_min: str | None = None,
    time_max: str | None = None,
    tz: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    start, end = _range(time_min, time_max, view)
    items = calendars.list_events(db, user.id, time_min=start, time_max=end, timezone_name=_tz(tz))
    return {"items": items, "time_min": start, "time_max": end, "view": view}


@router.post("/events")
def calendar_create(
    payload: CalendarEventIn,
    tz: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    proposal = normalize_add_event(payload.model_dump())
    if not proposal:
        raise HTTPException(status_code=400, detail="Need a title, start, and end.")
    event = calendars.create_event(
        db,
        user.id,
        title=proposal["title"],
        start=proposal["start"],
        end=proposal["end"],
        timezone_name=_tz(tz),
        location=payload.location,
        meeting_url=payload.meeting_url,
        online=payload.online,
        color=payload.color,
        calendar_id=payload.calendar_id,
    )
    db.commit()
    return event


@router.patch("/events/{event_id}")
def calendar_patch(
    event_id: str,
    payload: CalendarEventPatchIn,
    tz: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    event = calendars.patch_event(
        db,
        user.id,
        event_id,
        title=payload.title,
        start=payload.start,
        end=payload.end,
        timezone_name=_tz(tz),
        location=payload.location,
        meeting_url=payload.meeting_url,
        online=payload.online,
        color=payload.color,
        calendar_id=payload.calendar_id,
    )
    db.commit()
    return event


@router.delete("/events/{event_id}")
def calendar_delete(
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    calendars.delete_event(db, user.id, event_id)
    db.commit()
    return {"ok": True}
