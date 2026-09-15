from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.services import calendar_access as calendars
from app.services import fastmail_calendar as fmcal
from app.services import google_calendar as gcal
from app.services import google_oauth
from app.services.calendar_tool import normalize_add_event
from app.services.demo_lock import is_locked, reject_locked

router = APIRouter(prefix="/calendar", tags=["calendar"])

STATE_COOKIE = "sk_gcal_state"


class CalendarEventIn(BaseModel):
    title: str = Field(min_length=1, max_length=400)
    start: str
    end: str


class CalendarEventPatchIn(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=400)
    start: str | None = None
    end: str | None = None


def _origin(request: Request) -> str:
    return google_oauth.public_origin(
        str(request.base_url),
        request.headers.get("x-forwarded-proto"),
        request.headers.get("x-forwarded-host"),
        request.headers.get("host"),
    )


def _tz(value: str | None) -> str:
    name = (value or "").strip() or "UTC"
    return name[:80]


class FastmailConnectIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    token: str = Field(min_length=8, max_length=400)


@router.get("/status")
def calendar_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return calendars.status_payload(db, user.id, demo_locked=is_locked(user))


@router.get("/connect")
def calendar_connect(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    del db
    reject_locked(user)
    origin = _origin(request)
    state = google_oauth.encode_oauth_state(user.id)
    url = google_oauth.authorize_url(origin=origin, state=state)
    redirect = RedirectResponse(url, status_code=302)
    redirect.set_cookie(
        STATE_COOKIE,
        state,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=600,
        path="/",
    )
    return redirect


@router.get("/callback")
def calendar_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    origin = _origin(request)
    home = f"{origin}/#calendar"
    if error:
        return RedirectResponse(f"{home}?calendar_error=denied", status_code=302)
    cookie_state = request.cookies.get(STATE_COOKIE)
    if not code or not state or not cookie_state or cookie_state != state:
        return RedirectResponse(f"{home}?calendar_error=state", status_code=302)
    user_id = google_oauth.decode_oauth_state(state)
    user = db.get(User, user_id)
    if not user or is_locked(user):
        return RedirectResponse(f"{home}?calendar_error=demo", status_code=302)
    try:
        tokens = google_oauth.exchange_code(code, origin)
        gcal.store_tokens(
            db,
            user.id,
            access_token=str(tokens["access_token"]),
            refresh_token=tokens.get("refresh_token") if isinstance(tokens.get("refresh_token"), str) else None,
            expiry=tokens["expiry"],  # type: ignore[arg-type]
            scope=str(tokens.get("scope") or google_oauth.CALENDAR_EVENTS_SCOPE),
            google_sub=None,
            google_email=None,
        )
        gcal.remember_profile(db, user.id, str(tokens["access_token"]))
        db.commit()
    except HTTPException:
        db.rollback()
        return RedirectResponse(f"{home}?calendar_error=token", status_code=302)
    redirect = RedirectResponse(home, status_code=302)
    redirect.delete_cookie(STATE_COOKIE, path="/")
    return redirect


@router.post("/fastmail/connect")
def calendar_fastmail_connect(
    payload: FastmailConnectIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    reject_locked(user)
    row = fmcal.connect(db, user.id, email=payload.email, token=payload.token)
    db.commit()
    return {
        "ok": True,
        "connected": True,
        "provider": "fastmail",
        "fastmail_email": row.fastmail_email,
        "calendar_name": row.calendar_name,
    }


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
