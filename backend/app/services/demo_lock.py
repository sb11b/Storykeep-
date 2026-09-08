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
