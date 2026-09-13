from __future__ import annotations

import os

from fastapi import HTTPException, status

from app.models import User

LOCKED_DEMO_EMAILS = frozenset(
    {
        "steve@storykeep.local",
        *(part.strip().lower() for part in os.getenv("DEMO_LOCKED_EMAILS", "").split(",") if part.strip()),
    }
)

PROTECTED_EMAILS = frozenset({"stevebitsko@duck.com"})


def email_is_locked(email: str | None) -> bool:
    value = (email or "").strip().lower()
    if not value or value in PROTECTED_EMAILS:
        return False
    return value in LOCKED_DEMO_EMAILS


def is_locked(user: User | None) -> bool:
    if user is None:
        return False
    email = (user.email or "").strip().lower()
    if email in PROTECTED_EMAILS:
        return False
    if email_is_locked(email):
        return True
    return bool(getattr(user, "is_demo_locked", False))


def reject_locked(user: User) -> None:
    if is_locked(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo account closed")


def reject_authentication(user: User | None) -> None:
    """Block sign-in and invalidate existing sessions for closed demo accounts."""
    if user is not None and is_locked(user):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Demo account closed")


def profile_is_read_only(user: User | None) -> bool:
    return is_locked(user)


def reject_profile_mutation(user: User) -> None:
    if profile_is_read_only(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo account profile is read-only",
        )


def user_requires_2fa(user: User | None) -> bool:
    if user is None or is_locked(user):
        return False
    return bool(getattr(user, "totp_enabled", False) or getattr(user, "email_otp_enabled", False))
