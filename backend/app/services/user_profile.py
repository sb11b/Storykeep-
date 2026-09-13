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
        avatar_media_id=user.avatar_media_id,
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
        avatar_media_id=user.avatar_media_id,
        avatar_url=avatar_url_for(user),
        birthdate=user.birthdate,
        preferences=user.preferences or {},
        created_at=user.created_at,
        profile_read_only=profile_is_read_only(user),
        totp_enabled=bool(user.totp_enabled),
        email_otp_enabled=bool(user.email_otp_enabled),
        email_otp_available=mailer_configured(),
        has_backup_codes=bool(user.backup_code_hashes),
    )


def _read_theme_color(raw: dict, nested_key: str, preset_key: str, custom_key: str) -> dict | None:
    nested = raw.get(nested_key)
    if isinstance(nested, dict):
        preset = nested.get("preset")
        custom = nested.get("custom")
        if preset or custom:
            return {"preset": preset, "custom": custom}
    preset = raw.get(preset_key)
    custom = raw.get(custom_key)
    if preset or custom:
        return {"preset": preset, "custom": custom}
    return None


def normalize_appearance_storage(raw: dict) -> dict:
    out: dict = {}
    for nested_key, preset_key, custom_key in (
        ("pageBg", "page_preset", "page_custom"),
        ("topBar", "topbar_preset", "topbar_custom"),
        ("rail", "rail_preset", "rail_custom"),
    ):
        color = _read_theme_color(raw, nested_key, preset_key, custom_key)
        if color:
            out[nested_key] = {key: value for key, value in color.items() if value is not None}
    if raw.get("font_family"):
        out["font_family"] = raw["font_family"]
    if raw.get("base_font_size"):
        out["base_font_size"] = raw["base_font_size"]
    return out


def merge_appearance_preferences(preferences: dict, appearance: dict | None) -> dict:
    current = dict(preferences or {})
    if not appearance:
        return current
    merged = dict(current.get("appearance") or {})
    normalized = normalize_appearance_storage(appearance)
    for key, value in normalized.items():
        if key in {"pageBg", "topBar", "rail"} and isinstance(value, dict):
            slot = dict(merged.get(key) or {})
            slot.update(value)
            merged[key] = slot
        elif value is not None:
            merged[key] = value
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
