from __future__ import annotations

import base64
import secrets
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import GrokMessage, User

PREF_ENABLED = "message_crypto_enabled"
PREF_SALT = "message_crypto_salt"


def _prefs(user: User) -> dict[str, Any]:
    return getattr(user, "preferences", None) or {}


def is_enabled(user: User) -> bool:
    return bool(_prefs(user).get(PREF_ENABLED))


def salt_b64(user: User) -> str | None:
    raw = _prefs(user).get(PREF_SALT)
    if not isinstance(raw, str) or not raw.strip():
        return None
    return raw.strip()


def enable(db: Session, user: User, *, salt_b64_value: str | None = None) -> dict[str, Any]:
    prefs = dict(_prefs(user))
    if not prefs.get(PREF_SALT):
        if salt_b64_value:
            prefs[PREF_SALT] = salt_b64_value.strip()
        else:
            prefs[PREF_SALT] = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
    prefs[PREF_ENABLED] = True
    user.preferences = prefs
    db.add(user)
    db.flush()
    return status(db, user)


def status(db: Session, user: User) -> dict[str, Any]:
    return {
        "enabled": is_enabled(user),
        "salt": salt_b64(user),
        "plaintext_count": plaintext_message_count(db, user.id),
    }


def plaintext_message_count(db: Session, user_id: UUID) -> int:
    from app.models import GrokConversation

    return int(
        db.scalar(
            select(func.count())
            .select_from(GrokMessage)
            .join(GrokConversation, GrokMessage.conversation_id == GrokConversation.id)
            .where(
                GrokConversation.user_id == user_id,
                GrokMessage.encrypted.is_(False),
                GrokMessage.content.isnot(None),
            )
        )
        or 0
    )


def validate_ciphertext(iv: str, ct: str) -> None:
    if not (iv or "").strip() or not (ct or "").strip():
        raise ValueError("iv and ct are required.")
    try:
        iv_bytes = base64.b64decode(iv.strip(), validate=True)
        ct_bytes = base64.b64decode(ct.strip(), validate=True)
    except Exception as exc:
        raise ValueError("iv and ct must be valid base64.") from exc
    if len(iv_bytes) != 12:
        raise ValueError("iv must decode to 12 bytes.")
    if len(ct_bytes) < 16:
        raise ValueError("ct is too short.")


def message_body_out(row: GrokMessage, *, crypto_enabled: bool) -> dict[str, Any]:
    if row.encrypted:
        return {"encrypted": True, "iv": row.body_iv or "", "ct": row.body_ct or "", "content": None}
    if crypto_enabled:
        return {"encrypted": False, "iv": None, "ct": None, "content": row.content or ""}
    return {"encrypted": False, "iv": None, "ct": None, "content": row.content or ""}
