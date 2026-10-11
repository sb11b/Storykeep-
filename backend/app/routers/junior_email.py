from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.schemas import (
    JuniorEmailBodyOut,
    JuniorEmailDraftIn,
    JuniorEmailDraftOut,
    JuniorEmailMessageOut,
    JuniorDocumentFileTextOut,
)
from app.services import fastmail_jmap as jmap
from app.services import file_extract
from app.services import junior_shared_files
from app.services import mail as mail_service
from app.services.junior_shared_common import normalize_slug

router = APIRouter(tags=["junior-shared-email"])

EMAIL_UNAVAILABLE = "Email is not connected."
# A full email body for reading aloud; real bodies are far shorter than this.
BODY_EXCERPT_CHARS = 8_000
# A school-text file (textbook chapter, long reading) read aloud; files run
# much longer than emails, so the cap is higher. Truncated text is marked.
FILE_TEXT_CAP = 30_000


def require_email_token(db: Session, user: User) -> str:
    """Resolve the JMAP token: stored per-user token, then env (JMAP or legacy).
    503 (never a crash) when nothing is configured."""
    token = (
        mail_service.stored_mail_token(db, user.id)
        or mail_service.stored_app_password(db, user.id)
        or mail_service.env_token()
    )
    if not token:
        raise HTTPException(status_code=503, detail=EMAIL_UNAVAILABLE)
    return token


# ── Pure mappers: JMAP service payloads -> voice-friendly DTOs ───────────────


def map_inbox_items(payload: dict) -> list[JuniorEmailMessageOut]:
    out: list[JuniorEmailMessageOut] = []
    for row in payload.get("items") or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        out.append(
            JuniorEmailMessageOut(
                id=str(row["id"]),
                from_address=str(row.get("from") or ""),
                to=str(row.get("to") or ""),
                subject=str(row.get("subject") or ""),
                date=str(row.get("date") or ""),
                preview=str(row.get("preview") or "")[:200],
                unread=bool(row.get("unseen")),
            )
        )
    return out


def map_email_body(payload: dict) -> JuniorEmailBodyOut:
    body = str(payload.get("body") or "")
    return JuniorEmailBodyOut(
        id=str(payload.get("id") or ""),
        from_address=str(payload.get("from") or ""),
        to=str(payload.get("to") or ""),
        cc=str(payload.get("cc") or ""),
        subject=str(payload.get("subject") or ""),
        date=str(payload.get("date") or ""),
        body=body[:BODY_EXCERPT_CHARS],
        excerpt=len(body) > BODY_EXCERPT_CHARS,
    )


def map_draft_created(payload: dict) -> JuniorEmailDraftOut:
    return JuniorEmailDraftOut(
        id=str(payload.get("id") or ""),
        to=str(payload.get("to") or ""),
        subject=str(payload.get("subject") or ""),
        from_address=str(payload.get("from") or ""),
        draft=True,
    )


def map_file_text(filename: str, text: str, *, cap: int = FILE_TEXT_CAP) -> JuniorDocumentFileTextOut:
    """Pure mapping: extracted file text -> capped DTO with excerpt marker."""
    cleaned = text or ""
    return JuniorDocumentFileTextOut(
        file_id="",
        slug="",
        filename=filename,
        text=cleaned[:cap],
        excerpt=len(cleaned) > cap,
    )


# ── Routes (all behind require_user) ─────────────────────────────────────────


@router.get("/email/inbox", response_model=list[JuniorEmailMessageOut])
def email_inbox(
    limit: int = Query(default=10, ge=1, le=50),
    folder: str = Query(default="inbox", max_length=32),
    unread_only: bool = Query(default=False, alias="unread_only"),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[JuniorEmailMessageOut]:
    token = require_email_token(db, user)
    payload = jmap.list_emails(token, role=folder, unseen=unread_only, limit=limit)
    return map_inbox_items(payload)


@router.get("/email/search", response_model=list[JuniorEmailMessageOut])
def email_search(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=10, ge=1, le=25),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[JuniorEmailMessageOut]:
    token = require_email_token(db, user)
    payload = jmap.search_emails(token, query=q, limit=limit)
    return map_inbox_items(payload)


@router.get("/email/message/{message_id}", response_model=JuniorEmailBodyOut)
def email_message(
    message_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorEmailBodyOut:
    token = require_email_token(db, user)
    payload = jmap.get_email(token, message_id)
    return map_email_body(payload)


@router.get("/email/drafts", response_model=list[JuniorEmailMessageOut])
def email_drafts(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[JuniorEmailMessageOut]:
    token = require_email_token(db, user)
    payload = jmap.list_emails(token, role="drafts", unseen=False, limit=limit)
    return map_inbox_items(payload)


@router.post("/email/draft", response_model=JuniorEmailDraftOut, status_code=201)
def email_draft(
    payload: JuniorEmailDraftIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorEmailDraftOut:
    """Save a DRAFT in Fastmail. This route never sends — there is no
    EmailSubmission/set call anywhere in the junior email surface; sending
    stays a human action in Fastmail."""
    token = require_email_token(db, user)
    created = jmap.create_draft(
        token,
        to=payload.to,
        subject=payload.subject,
        body=payload.body,
        reply_to_message_id=payload.reply_to_message_id,
    )
    return map_draft_created(created)


@router.get(
    "/documents/{slug}/files/{file_id}/text",
    response_model=JuniorDocumentFileTextOut,
)
def document_file_text(
    slug: str,
    file_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorDocumentFileTextOut:
    """Extract text from a document's attached file so Junior can read it aloud.

    Reuses the shared file_extract pipeline (python-docx for Word, plain text
    for .txt/.md). Unsupported types come back as a speakable 415."""
    try:
        file_uuid = uuid.UUID(file_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="File not found.") from exc
    row = junior_shared_files.get_file(db, user, file_uuid)
    if normalize_slug(slug) != row.document_slug:
        raise HTTPException(status_code=404, detail="File not found.")
    try:
        payload = Path(row.storage_path).read_bytes()
    except OSError as exc:
        raise HTTPException(status_code=502, detail="That file is no longer on disk.") from exc
    try:
        _title, text = file_extract.extract_document(row.filename, payload)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    mapped = map_file_text(row.filename, text)
    mapped.file_id = str(row.id)
    mapped.slug = row.document_slug
    return mapped
