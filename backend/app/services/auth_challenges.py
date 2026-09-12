from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import hash_password, verify_password
from app.config import settings
from app.models import AuthChallenge, User
from app.services.mailer import mailer_configured, send_email


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _expires(minutes: int | None = None) -> datetime:
    ttl = minutes if minutes is not None else settings.login_2fa_challenge_minutes
    return _now() + timedelta(minutes=ttl)


def _generate_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def create_login_challenge(db: Session, user: User) -> AuthChallenge:
    db.execute(delete(AuthChallenge).where(AuthChallenge.user_id == user.id, AuthChallenge.kind == "login_2fa"))
    row = AuthChallenge(
        user_id=user.id,
        kind="login_2fa",
        code_hash=None,
        payload={},
        expires_at=_expires(),
    )
    db.add(row)
    db.flush()
    if user.email_otp_enabled and mailer_configured():
        code = _generate_code()
        row.code_hash = hash_password(code)
        db.add(row)
        send_email(
            user.email,
            "Your Storykeep sign-in code",
            f"Your Storykeep sign-in code is {code}. It expires in {settings.login_2fa_challenge_minutes} minutes.",
        )
    db.flush()
    return row


def create_email_change_challenge(db: Session, user: User, new_email: str) -> AuthChallenge:
    if not mailer_configured():
        raise HTTPException(status_code=503, detail="Email verification is not configured on this server")
    db.execute(delete(AuthChallenge).where(AuthChallenge.user_id == user.id, AuthChallenge.kind == "email_change"))
    code = _generate_code()
    row = AuthChallenge(
        user_id=user.id,
        kind="email_change",
        code_hash=hash_password(code),
        payload={"new_email": new_email.lower()},
        expires_at=_expires(30),
    )
    db.add(row)
    db.flush()
    send_email(
        new_email,
        "Confirm your new Storykeep email",
        f"Your Storykeep email confirmation code is {code}. It expires in 30 minutes.",
    )
    return row


def _load_challenge(db: Session, challenge_id: UUID, *, kind: str) -> AuthChallenge:
    row = db.get(AuthChallenge, challenge_id)
    if not row or row.kind != kind:
        raise HTTPException(status_code=401, detail="Sign-in challenge expired or invalid")
    if row.expires_at < _now():
        db.delete(row)
        db.flush()
        raise HTTPException(status_code=401, detail="Sign-in challenge expired or invalid")
    return row


def verify_login_email_code(db: Session, challenge: AuthChallenge, code: str) -> bool:
    if not challenge.code_hash:
        return False
    if challenge.attempts >= settings.login_email_otp_max_attempts:
        raise HTTPException(status_code=401, detail="Too many incorrect codes")
    challenge.attempts += 1
    db.add(challenge)
    if not verify_password(code.strip(), challenge.code_hash):
        return False
    return True


def verify_email_change_code(db: Session, user: User, code: str) -> str:
    row = db.scalar(
        select(AuthChallenge).where(
            AuthChallenge.user_id == user.id,
            AuthChallenge.kind == "email_change",
        )
    )
    if not row or row.expires_at < _now():
        raise HTTPException(status_code=400, detail="Email confirmation code expired")
    if row.attempts >= settings.login_email_otp_max_attempts:
        raise HTTPException(status_code=400, detail="Too many incorrect codes")
    row.attempts += 1
    db.add(row)
    if not row.code_hash or not verify_password(code.strip(), row.code_hash):
        raise HTTPException(status_code=400, detail="Incorrect confirmation code")
    new_email = str((row.payload or {}).get("new_email") or "").strip().lower()
    if not new_email:
        raise HTTPException(status_code=400, detail="Email confirmation code expired")
    db.delete(row)
    return new_email


def consume_login_challenge(db: Session, challenge_id: UUID) -> User:
    challenge = _load_challenge(db, challenge_id, kind="login_2fa")
    user = db.get(User, challenge.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="Sign-in challenge expired or invalid")
    db.delete(challenge)
    return user
