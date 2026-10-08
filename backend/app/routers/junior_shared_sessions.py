from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.schemas import (
    JuniorAgentContextOut,
    JuniorDocumentOut,
    JuniorProjectOut,
    JuniorSessionIn,
    JuniorSessionOut,
    JuniorSharedMemoryOut,
    JuniorSharedMessageOut,
    JuniorSharedSearchHitOut,
)
from app.services import junior_shared_memory as store


router = APIRouter(tags=["junior-shared-sessions"])


def _page_headers(response: Response, next_cursor: str | None) -> None:
    response.headers["X-Has-More"] = "true" if next_cursor else "false"
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor


def _context_out(pack: dict) -> JuniorAgentContextOut:
    return JuniorAgentContextOut(
        project=JuniorProjectOut.model_validate(pack["project"]),
        thread_summary=pack.get("thread_summary"),
        recent_messages=[JuniorSharedMessageOut.model_validate(row) for row in pack.get("recent_messages") or []],
        memories=[JuniorSharedMemoryOut.model_validate(row) for row in pack.get("memories") or []],
        search_hits=[JuniorSharedSearchHitOut.model_validate(hit) for hit in pack.get("search_hits") or []],
        documents=[JuniorDocumentOut.model_validate(doc) for doc in pack.get("documents") or []],
        launch_hint=str(pack.get("launch_hint") or ""),
    )

@router.get("/sessions", response_model=list[JuniorSessionOut])
def list_sessions(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
    venue: str | None = Query(default=None, max_length=24),
) -> list[JuniorSessionOut]:
    rows, next_cursor = store.list_sessions_page(
        db, user, limit=limit, cursor=cursor, before_id=before_id, venue=venue
    )
    _page_headers(response, next_cursor)
    return [JuniorSessionOut.model_validate(row) for row in rows]


@router.get("/sessions/{session_id}", response_model=JuniorSessionOut)
def get_session(
    session_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSessionOut:
    return JuniorSessionOut.model_validate(store.session_owned(db, user, session_id))


@router.get("/threads/{thread_id}/sessions", response_model=list[JuniorSessionOut])
def list_thread_sessions(
    thread_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorSessionOut]:
    """Sessions on this thread (venue matches the thread). 404 if the thread is missing."""
    rows, next_cursor = store.list_thread_sessions_page(
        db, user, thread_id, limit=limit, cursor=cursor, before_id=before_id
    )
    _page_headers(response, next_cursor)
    return [JuniorSessionOut.model_validate(row) for row in rows]


@router.post("/threads/{thread_id}/sessions", response_model=JuniorSessionOut)
def heartbeat_thread_session(
    thread_id: UUID,
    payload: JuniorSessionIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSessionOut:
    """Heartbeat a session on this thread. Replay stays on this route, not POST /sessions."""
    incoming = payload or JuniorSessionIn()
    fields = incoming.model_fields_set
    row = store.touch_thread_session(
        db,
        user,
        thread_id,
        venue=incoming.venue if "venue" in fields else None,
        device_label=incoming.device_label if "device_label" in fields else None,
    )
    db.commit()
    db.refresh(row)
    return JuniorSessionOut.model_validate(row)


@router.get("/threads/{thread_id}/sessions/{session_id}", response_model=JuniorSessionOut)
def get_thread_session(
    thread_id: UUID,
    session_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSessionOut:
    """One session on this thread. 404 if the thread is missing or the venue does not match."""
    return JuniorSessionOut.model_validate(
        store.thread_session_owned(db, user, thread_id, session_id)
    )


@router.post("/threads/{thread_id}/sessions/{session_id}", response_model=JuniorSessionOut)
def update_thread_session(
    thread_id: UUID,
    session_id: UUID,
    payload: JuniorSessionIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSessionOut:
    """Update a session on this thread. Replay stays on this route, not POST /sessions/{id}."""
    incoming = payload or JuniorSessionIn()
    fields = incoming.model_fields_set
    row = store.update_thread_session(
        db,
        user,
        thread_id,
        session_id,
        venue=incoming.venue if "venue" in fields else None,
        device_label=incoming.device_label if "device_label" in fields else None,
        set_device_label="device_label" in fields,
    )
    db.commit()
    db.refresh(row)
    return JuniorSessionOut.model_validate(row)


@router.post("/sessions/{session_id}", response_model=JuniorSessionOut)
def update_session(
    session_id: UUID,
    payload: JuniorSessionIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSessionOut:
    incoming = payload or JuniorSessionIn()
    fields = incoming.model_fields_set
    row = store.update_session(
        db,
        user,
        session_id,
        venue=incoming.venue if "venue" in fields else None,
        device_label=incoming.device_label if "device_label" in fields else None,
        set_device_label="device_label" in fields,
    )
    db.commit()
    db.refresh(row)
    return JuniorSessionOut.model_validate(row)


@router.post("/sessions", response_model=JuniorSessionOut)
def heartbeat_session(
    payload: JuniorSessionIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSessionOut:
    incoming = payload or JuniorSessionIn()
    row = store.touch_session(db, user, incoming.venue, incoming.device_label)
    db.commit()
    db.refresh(row)
    return JuniorSessionOut.model_validate(row)


def _context_out(pack: dict) -> JuniorAgentContextOut:
    return JuniorAgentContextOut(
        project=JuniorProjectOut.model_validate(pack["project"]),
        thread_summary=pack.get("thread_summary"),
        recent_messages=[JuniorSharedMessageOut.model_validate(row) for row in pack.get("recent_messages") or []],
        memories=[JuniorSharedMemoryOut.model_validate(row) for row in pack.get("memories") or []],
        search_hits=[JuniorSharedSearchHitOut.model_validate(hit) for hit in pack.get("search_hits") or []],
        documents=[JuniorDocumentOut.model_validate(doc) for doc in pack.get("documents") or []],
        launch_hint=str(pack.get("launch_hint") or ""),
    )


