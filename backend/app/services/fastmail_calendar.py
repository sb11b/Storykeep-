from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import FastmailCalendarAccount
from app.services import fastmail_caldav as caldav
from app.services.crypto_box import decrypt_secret, encrypt_secret


def is_connected(db: Session, user_id: UUID) -> bool:
    row = db.get(FastmailCalendarAccount, user_id)
    return bool(row and row.token_encrypted)


def status_payload(db: Session, user_id: UUID, *, demo_locked: bool) -> dict[str, object]:
    row = db.get(FastmailCalendarAccount, user_id)
    return {
        "connected": bool(row and row.token_encrypted) and not demo_locked,
        "fastmail_email": row.fastmail_email if row and not demo_locked else None,
        "calendar_name": row.calendar_name if row and not demo_locked else None,
    }


def _row(db: Session, user_id: UUID) -> FastmailCalendarAccount:
    row = db.get(FastmailCalendarAccount, user_id)
    if not row or not row.token_encrypted:
        raise HTTPException(status_code=409, detail="Connect Fastmail Calendar first.")
    return row


def _creds(db: Session, user_id: UUID) -> tuple[FastmailCalendarAccount, str]:
    row = _row(db, user_id)
    token = decrypt_secret(row.token_encrypted)
    if not token:
        raise HTTPException(status_code=401, detail="Fastmail Calendar needs to be connected again.")
    return row, token


def connect(db: Session, user_id: UUID, *, email: str, token: str) -> FastmailCalendarAccount:
    address = (email or "").strip()
    secret = (token or "").strip()
    if "@" not in address or len(address) > 320:
        raise HTTPException(status_code=400, detail="Use your Fastmail email address.")
    if len(secret) < 8 or len(secret) > 400:
        raise HTTPException(status_code=400, detail="Use a Fastmail app password or API token, never the account password.")
    discovered = caldav.discover_calendar(address, secret)
    row = db.get(FastmailCalendarAccount, user_id)
    if row is None:
        row = FastmailCalendarAccount(user_id=user_id, token_encrypted="", fastmail_email=address)
        db.add(row)
    row.fastmail_email = discovered["email"]
    row.token_encrypted = encrypt_secret(secret)
    row.calendar_href = discovered["calendar_href"]
    row.calendar_name = discovered["calendar_name"]
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return row


def disconnect(db: Session, user_id: UUID) -> None:
    row = db.get(FastmailCalendarAccount, user_id)
    if not row:
        return
    db.delete(row)
    db.flush()


def list_events(db: Session, user_id: UUID, *, time_min: str, time_max: str) -> list[dict[str, object]]:
    row, token = _creds(db, user_id)
    return caldav.list_events(row.fastmail_email, token, row.calendar_href, time_min=time_min, time_max=time_max)


def create_event(
    db: Session,
    user_id: UUID,
    *,
    title: str,
    start: str,
    end: str,
) -> dict[str, object]:
    row, token = _creds(db, user_id)
    return caldav.create_event(
        row.fastmail_email,
        token,
        row.calendar_href,
        title=title,
        start=start,
        end=end,
    )


def patch_event(
    db: Session,
    user_id: UUID,
    event_id: str,
    *,
    title: str | None,
    start: str | None,
    end: str | None,
) -> dict[str, object]:
    row, token = _creds(db, user_id)
    return caldav.patch_event(
        row.fastmail_email,
        token,
        event_id,
        title=title,
        start=start,
        end=end,
    )


def delete_event(db: Session, user_id: UUID, event_id: str) -> None:
    row, token = _creds(db, user_id)
    caldav.delete_event(row.fastmail_email, token, event_id)
