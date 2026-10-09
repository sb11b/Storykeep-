from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.routers.chat import _message_out
from app.schemas import GrokMessageOut
from app.services import chat_attachments
from app.services import chat_docx
from app.services import grok_conversations as grok_store
from app.services import message_crypto

router = APIRouter(prefix="/chat", tags=["chat"])


class EncryptedMessageIn(BaseModel):
    role: str = Field(max_length=16)
    iv: str = Field(min_length=8, max_length=32)
    ct: str = Field(min_length=8, max_length=500_000)
    id: UUID | None = None
    title: str | None = Field(default=None, max_length=80)
    media_ids: list[UUID] = Field(default_factory=list, max_length=5)


class SnippetIn(BaseModel):
    code: str = Field(min_length=1, max_length=4000)


@router.post("/conversations/{conversation_id}/messages", response_model=GrokMessageOut, status_code=201)
def post_encrypted_message(
    conversation_id: UUID,
    payload: EncryptedMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> GrokMessageOut:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    if not message_crypto.is_enabled(user):
        raise HTTPException(status_code=400, detail="Message encryption is not enabled.")
    if payload.role not in {"user", "assistant"}:
        raise HTTPException(status_code=400, detail="role must be user or assistant.")
    conversation = grok_store.owned_conversation(db, user, conversation_id)
    row = grok_store.append_encrypted_message(
        db,
        conversation,
        role=payload.role,
        iv=payload.iv,
        ct=payload.ct,
        message_id=payload.id,
        title=payload.title if payload.role == "user" else None,
    )
    if payload.media_ids:
        chat_attachments.attach_to_message(db, user, row, payload.media_ids)
    db.commit()
    db.refresh(row)
    return _message_out(row, crypto_enabled=True)


@router.post("/messages/{message_id}/docx")
def download_message_docx(
    message_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    clean: bool = Query(default=False),
) -> Response:
    if not grok_store.should_persist(user):
        raise HTTPException(status_code=403, detail="Chat history is not stored for demo accounts.")
    row = grok_store.owned_assistant_message(db, user, message_id)
    if row.encrypted or row.content is None:
        raise HTTPException(status_code=400, detail="Encrypted messages must be exported in the browser.")
    content = row.content
    if clean:
        from app.services.school_tools import strip_marks

        content = strip_marks(content)
    if not chat_docx.has_word_body(content):
        raise HTTPException(status_code=400, detail=chat_docx.EMPTY_WORD_BODY)
    try:
        payload = chat_docx.build_message_docx(content)
    except ValueError as exc:
        detail = str(exc).strip() or chat_docx.BUILD_WORD_FAIL
        if detail == chat_docx.EMPTY_WORD_BODY:
            raise HTTPException(status_code=400, detail=chat_docx.EMPTY_WORD_BODY) from exc
        raise HTTPException(status_code=400, detail=chat_docx.BUILD_WORD_FAIL) from exc
    filename = chat_docx.docx_filename(content).replace('"', "")
    return Response(
        content=payload,
        media_type=chat_docx.DOCX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/messages/{message_id}/run-snippet")
def run_message_snippet(
    message_id: UUID,
    payload: SnippetIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    from app.services import junior_jobs as jobs

    result = jobs.run_snippet(db, user, message_id, payload.code)
    return {
        "conversation_id": str(result["conversation_id"]),
        "user_message": GrokMessageOut.model_validate(result["user_message"]).model_dump(mode="json"),
        "assistant_message": GrokMessageOut.model_validate(result["assistant_message"]).model_dump(mode="json"),
    }
