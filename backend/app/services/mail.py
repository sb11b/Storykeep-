from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models import FastmailMailAccount, User
from app.services import fastmail_jmap as jmap
from app.services.crypto_box import decrypt_secret, encrypt_secret
from app.services.demo_lock import is_locked
from app.services.junior_memory import OWNER_EMAIL, owner_email

CONNECT_DETAIL = "Connect Fastmail"
OWNER_ONLY_DETAIL = "Mail is only available on the owner account."
DEMO_DETAIL = "Demo accounts cannot use mail."


def is_mail_owner(user: User | None) -> bool:
    return owner_email(user) == OWNER_EMAIL


def env_token() -> str:
    return (settings.fastmail_token or "").strip()


def stored_token(db: Session, user_id: UUID) -> str:
    row = db.get(FastmailMailAccount, user_id)
    raw = getattr(row, "token_encrypted", None) if row else None
    if not isinstance(raw, str) or not raw.strip():
        return ""
    return (decrypt_secret(raw) or "").strip()


def has_token(db: Session, user: User) -> bool:
    if not is_mail_owner(user) or is_locked(user):
        return False
    return bool(env_token() or stored_token(db, user.id))


def require_owner(user: User) -> None:
    if is_locked(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=DEMO_DETAIL)
    if not is_mail_owner(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=OWNER_ONLY_DETAIL)


def require_token(db: Session, user: User) -> str:
    require_owner(user)
    token = env_token() or stored_token(db, user.id)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=CONNECT_DETAIL)
    return token


def status_payload(db: Session, user: User) -> dict[str, object]:
    demo = is_locked(user)
    owner = is_mail_owner(user)
    token = env_token() if owner and not demo else ""
    source = "env" if token else None
    if owner and not demo and not token and stored_token(db, user.id):
        token = stored_token(db, user.id)
        source = "account"
    connected = bool(token) and owner and not demo
    email = None
    boxes: list[dict[str, object]] = []
    if connected:
        try:
            session, _, boxes = jmap.mailboxes(token)
            email = str(session.get("username") or "") or None
        except HTTPException:
            connected = False
            boxes = []
    return {
        "configured": bool(env_token()) or bool(owner and stored_token(db, user.id)),
        "connected": connected,
        "owner_only": True,
        "is_owner": owner,
        "demo_locked": demo,
        "fastmail_email": email if connected else None,
        "source": source if connected else None,
        "mailboxes": boxes if connected else [],
        "connect_detail": CONNECT_DETAIL,
    }


def connect(db: Session, user: User, *, token: str) -> FastmailMailAccount:
    require_owner(user)
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
    require_owner(user)
    row = db.get(FastmailMailAccount, user.id)
    if row:
        db.delete(row)
        db.flush()
    jmap._session_cache.clear()
