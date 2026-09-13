from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NoteMedia, User
from app.schemas import ProfileOut, UserOut
from app.services.demo_lock import profile_is_read_only
from app.services.mailer import mailer_configured
from app.services.note_media import is_image_media, owned_media


def avatar_url_for(user: User) -> str | None:
    if user.avatar_media_id:
        return f"/api/v1/media/{user.avatar_media_id}"
    return None


def user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=avatar_url_for(user),
        birthdate=user.birthdate,
        preferences=user.preferences or {},
        profile_read_only=profile_is_read_only(user),
        created_at=user.created_at,
    )


def profile_out(user: User) -> ProfileOut:
    return ProfileOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        avatar_url=avatar_url_for(user),
        birthdate=user.birthdate,
        preferences=user.preferences or {},
        profile_read_only=profile_is_read_only(user),
        totp_enabled=bool(user.totp_enabled),
        email_otp_enabled=bool(user.email_otp_enabled),
        email_otp_available=mailer_configured(),
        has_backup_codes=bool(user.backup_code_hashes),
    )


def merge_appearance_preferences(preferences: dict, appearance: dict | None) -> dict:
    current = dict(preferences or {})
    if not appearance:
        return current
    merged = dict(current.get("appearance") or {})
    merged.update({key: value for key, value in appearance.items() if value is not None})
    current["appearance"] = merged
    return current


def set_avatar_media(db: Session, user: User, media_id: UUID | None) -> None:
    if media_id is None:
        user.avatar_media_id = None
        return
    row = owned_media(db, user, media_id)
    if not is_image_media(row):
        raise HTTPException(status_code=400, detail="Profile photo must be an image")
    user.avatar_media_id = row.id


def parse_birthdate(value: date | None) -> date | None:
    return value
