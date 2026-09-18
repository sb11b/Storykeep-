from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.schemas import JuniorChatOut
from app.services import chat_index

router = APIRouter(prefix="/junior", tags=["junior-chats"])


def _row_out(row: dict) -> JuniorChatOut:
    note_raw = row.get("note_id")
    note_id = UUID(note_raw) if note_raw else None
    return JuniorChatOut(
        id=UUID(str(row["id"])),
        date=str(row.get("date") or ""),
        title=str(row.get("title") or "New chat"),
        summary=str(row.get("summary") or ""),
        note_id=note_id,
        messages=int(row.get("messages") or 0),
    )


@router.get("/chats", response_model=list[JuniorChatOut])
def list_chats(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[JuniorChatOut]:
    return [_row_out(row) for row in chat_index.chats_for(db, user)]
