from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.schemas import (
    JuniorSharedMessageIn,
    JuniorSharedMessageOut,
    JuniorSharedMessagePostOut,
    JuniorSharedThreadIn,
    JuniorSharedThreadOut,
)
from app.services import junior_shared_memory as store


router = APIRouter(tags=["junior-shared-threads"])


def _turn_out(thread_id: UUID, user_row, junior_row, reply_status: str) -> JuniorSharedMessagePostOut:
    return JuniorSharedMessagePostOut(
        thread_id=thread_id,
        user_message=JuniorSharedMessageOut.model_validate(user_row),
        junior_message=JuniorSharedMessageOut.model_validate(junior_row) if junior_row else None,
        reply_status=reply_status,
        detail=store.REPLY_STUB_DETAIL if junior_row is None else None,
    )


def _page_headers(response: Response, next_cursor: str | None) -> None:
    response.headers["X-Has-More"] = "true" if next_cursor else "false"
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor

@router.get("/threads", response_model=list[JuniorSharedThreadOut])
def list_threads(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorSharedThreadOut]:
    rows, next_cursor = store.list_threads_page(
        db, user, limit=limit, cursor=cursor, before_id=before_id
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedThreadOut.model_validate(row) for row in rows]


@router.post("/threads")
def create_thread(
    payload: JuniorSharedThreadIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedThreadOut | JuniorSharedMessagePostOut:
    first = (payload.content or payload.text or "").strip()
    if first:
        row = store.create_thread(db, user, title=payload.title, venue=payload.venue, status_value=payload.status)
        thread, user_row, junior_row, reply_status = store.post_turn(
            db,
            user,
            thread_id=row.id,
            content=first,
            venue=payload.venue,
            meta=payload.meta,
            device_label=payload.device_label,
        )
        db.commit()
        db.refresh(user_row)
        if junior_row is not None:
            db.refresh(junior_row)
        return _turn_out(thread.id, user_row, junior_row, reply_status)
    row = store.create_thread(db, user, title=payload.title, venue=payload.venue, status_value=payload.status)
    db.commit()
    db.refresh(row)
    return JuniorSharedThreadOut.model_validate(row)


@router.get("/threads/{thread_id}", response_model=JuniorSharedThreadOut)
def get_thread(
    thread_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedThreadOut:
    return JuniorSharedThreadOut.model_validate(store.thread_owned(db, user, thread_id))


@router.post("/threads/{thread_id}", response_model=JuniorSharedThreadOut)
def update_thread(
    thread_id: UUID,
    payload: JuniorSharedThreadIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedThreadOut:
    row = store.update_thread(
        db,
        user,
        thread_id,
        title=payload.title if "title" in payload.model_fields_set else None,
        status_value=payload.status if "status" in payload.model_fields_set else None,
    )
    db.commit()
    db.refresh(row)
    return JuniorSharedThreadOut.model_validate(row)


@router.get("/threads/{thread_id}/messages", response_model=list[JuniorSharedMessageOut])
def list_messages(
    thread_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorSharedMessageOut]:
    rows, next_cursor = store.list_messages_page(
        db, user, thread_id, limit=limit, cursor=cursor, before_id=before_id
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedMessageOut.model_validate(row) for row in rows]


@router.get("/threads/{thread_id}/messages/{message_id}", response_model=JuniorSharedMessageOut)
def get_thread_message(
    thread_id: UUID,
    message_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMessageOut:
    return JuniorSharedMessageOut.model_validate(
        store.thread_message_owned(db, user, thread_id, message_id)
    )


@router.post("/threads/{thread_id}/messages/{message_id}", response_model=JuniorSharedMessageOut)
def update_thread_message(
    thread_id: UUID,
    message_id: UUID,
    payload: JuniorSharedMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMessageOut:
    fields = payload.model_fields_set
    row = store.update_thread_message(
        db,
        user,
        thread_id,
        message_id,
        content=payload.body or None,
        venue=payload.venue if "venue" in fields else None,
        meta=payload.meta if "meta" in fields else None,
        set_venue="venue" in fields,
        set_meta="meta" in fields,
    )
    db.commit()
    db.refresh(row)
    return JuniorSharedMessageOut.model_validate(row)


