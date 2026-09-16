from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models import FastmailCalendarAccount, FastmailMailAccount, User
from app.services import fastmail_jmap as jmap
from app.services.crypto_box import decrypt_secret, encrypt_secret
from app.services.demo_lock import is_locked

CONNECT_DETAIL = "Connect Fastmail"
DEMO_DETAIL = "Mail is not enabled on this account"


def env_token() -> str:
    return (settings.fastmail_token or "").strip()


def _decrypt_row_token(row: object | None) -> str:
    raw = getattr(row, "token_encrypted", None) if row is not None else None
    if not isinstance(raw, str) or not raw.strip():
        return ""
    return (decrypt_secret(raw) or "").strip()


def stored_mail_token(db: Session, user_id: UUID) -> str:
    return _decrypt_row_token(db.get(FastmailMailAccount, user_id))


def stored_app_password(db: Session, user_id: UUID) -> str:
    return _decrypt_row_token(db.get(FastmailCalendarAccount, user_id))


def has_token(db: Session, user: User) -> bool:
    """Stored JMAP token, stored CalDAV app password, or env token for a live StoryKeep login."""
    if user is None or is_locked(user):
        return False
    if stored_mail_token(db, user.id) or stored_app_password(db, user.id):
        return True
    return bool(env_token())


def require_mail_user(user: User) -> None:
    if is_locked(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=DEMO_DETAIL)


def require_token(db: Session, user: User) -> str:
    require_mail_user(user)
    if not has_token(db, user):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=CONNECT_DETAIL)
    return stored_mail_token(db, user.id) or stored_app_password(db, user.id) or env_token()


def status_payload(db: Session, user: User) -> dict[str, object]:
    demo = is_locked(user)
    connected = False
    email = None
    boxes: list[dict[str, object]] = []
    source = None
    if not demo and has_token(db, user):
        token = stored_mail_token(db, user.id) or stored_app_password(db, user.id) or env_token()
        if stored_mail_token(db, user.id):
            source = "account"
        elif stored_app_password(db, user.id):
            source = "account"
        elif env_token():
            source = "env"
        try:
            session, _, boxes = jmap.mailboxes(token)
            email = str(session.get("username") or "") or None
            connected = True
        except HTTPException:
            connected = False
            boxes = []
            source = None
    return {
        "configured": has_token(db, user) if not demo else False,
        "connected": connected,
        "demo_locked": demo,
        "fastmail_email": email if connected else None,
        "source": source if connected else None,
        "mailboxes": boxes if connected else [],
        "connect_detail": CONNECT_DETAIL,
        "disabled_detail": DEMO_DETAIL,
    }


def connect(db: Session, user: User, *, token: str) -> FastmailMailAccount:
    require_mail_user(user)
    secret = (token or "").strip()
    if len(secret) < 8 or len(secret) > 400:
        raise HTTPException(status_code=400, detail="Use a Fastmail API token, never the account password.")
    session = jmap.fetch_session(secret, connect=True)
    email = str(session.get("username") or "").strip()
    if not email:
        raise HTTPException(status_code=401, detail=CONNECT_DETAIL)
    row = db.get(FastmailMailAccount, user.id)
    if row is None:
        row = FastmailMailAccount(user_id=user.id, token_encrypted="", fastmail_email=email)
        db.add(row)
    row.fastmail_email = email
    row.token_encrypted = encrypt_secret(secret)
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    jmap._session_cache.clear()
    return row


def disconnect(db: Session, user: User) -> None:
    """Clear this user's stored Fastmail credentials. Does not end the StoryKeep session."""
    require_mail_user(user)
    mail_row = db.get(FastmailMailAccount, user.id)
    if mail_row:
        db.delete(mail_row)
    cal_row = db.get(FastmailCalendarAccount, user.id)
    if cal_row:
        db.delete(cal_row)
    db.flush()
    jmap._session_cache.clear()
