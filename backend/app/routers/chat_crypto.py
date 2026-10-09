from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.services import grok_conversations as grok_store
from app.services import message_crypto

router = APIRouter(prefix="/chat/crypto", tags=["chat"])


class MessageCryptoEnableIn(BaseModel):
    salt: str | None = Field(default=None, max_length=64)


class CryptoMigrateIn(BaseModel):
    messages: list[dict] = Field(min_length=1, max_length=200)


@router.get("")
def get_message_crypto(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    return message_crypto.status(db, user)


@router.post("/enable")
def enable_message_crypto(
    payload: MessageCryptoEnableIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    body = payload or MessageCryptoEnableIn()
    result = message_crypto.enable(db, user, salt_b64_value=body.salt)
    db.commit()
    return result


@router.post("/migrate")
def migrate_message_crypto(
    payload: CryptoMigrateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    if not message_crypto.is_enabled(user):
        raise HTTPException(status_code=400, detail="Message encryption is not enabled.")
    migrated = 0
    for item in payload.messages:
        message_id = item.get("id")
        iv = item.get("iv")
        ct = item.get("ct")
        if not message_id or not iv or not ct:
            raise HTTPException(status_code=400, detail="Each item needs id, iv, and ct.")
        try:
            mid = UUID(str(message_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid message id.") from exc
        grok_store.migrate_message_to_encrypted(db, user.id, mid, iv=str(iv), ct=str(ct))
        migrated += 1
    db.commit()
    return {"migrated": migrated, **message_crypto.status(db, user)}
