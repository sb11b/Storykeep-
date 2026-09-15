from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.services import fastmail_jmap as jmap
from app.services import mail as mail_service

router = APIRouter(prefix="/mail", tags=["mail"])


class MailConnectIn(BaseModel):
    token: str = Field(min_length=8, max_length=400)


class MailSendIn(BaseModel):
    to: str = Field(min_length=3, max_length=320)
    subject: str = Field(default="", max_length=400)
    body: str = Field(min_length=1, max_length=40_000)
    confirm: bool = False


@router.get("/status")
def mail_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return mail_service.status_payload(db, user)


@router.post("/connect")
def mail_connect(
    payload: MailConnectIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    row = mail_service.connect(db, user, token=payload.token)
    db.commit()
    return {"ok": True, "connected": True, "fastmail_email": row.fastmail_email}


@router.post("/disconnect")
def mail_disconnect(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    mail_service.disconnect(db, user)
    db.commit()
    return {"ok": True, "connected": False}


@router.get("/mailboxes")
def mail_mailboxes(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    token = mail_service.require_token(db, user)
    _, _, boxes = jmap.mailboxes(token)
    return {"items": boxes}


@router.get("/messages")
def mail_messages(
    mailbox_id: str | None = Query(default=None, max_length=200),
    role: str | None = Query(default="inbox", max_length=32),
    unseen: bool = Query(default=False),
    limit: int = Query(default=jmap.LIST_CAP, ge=1, le=jmap.LIST_CAP),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    token = mail_service.require_token(db, user)
    return jmap.list_emails(token, mailbox_id=mailbox_id, role=role, unseen=unseen, limit=limit)


@router.get("/messages/{email_id}")
def mail_message(
    email_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    token = mail_service.require_token(db, user)
    return jmap.get_email(token, email_id)


@router.post("/send")
def mail_send(
    payload: MailSendIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if not payload.confirm:
        raise HTTPException(status_code=400, detail="Confirm before sending.")
    token = mail_service.require_token(db, user)
    return jmap.send_email(token, to=payload.to, subject=payload.subject, body=payload.body)
