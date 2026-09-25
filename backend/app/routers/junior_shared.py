from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.schemas import (
    JuniorAgentContextOut,
    JuniorAgentLaunchIn,
    JuniorAgentLaunchOut,
    JuniorAgentRunOut,
    JuniorProjectIn,
    JuniorProjectOut,
    JuniorSharedContinueIn,
    JuniorSharedContinueOut,
    JuniorSharedMemoryIn,
    JuniorSharedMemoryOut,
    JuniorSharedMessageIn,
    JuniorSharedMessageOut,
    JuniorSharedMessagePostOut,
    JuniorSharedSearchHitOut,
    JuniorSharedThreadIn,
    JuniorSharedThreadOut,
)
from app.services import junior_shared_memory as store

router = APIRouter(
    prefix="/junior",
    tags=["junior-shared-memory"],
    dependencies=[Depends(require_user)],
)


def _turn_out(thread_id: UUID, user_row, junior_row, reply_status: str) -> JuniorSharedMessagePostOut:
    return JuniorSharedMessagePostOut(
        thread_id=thread_id,
        user_message=JuniorSharedMessageOut.model_validate(user_row),
        junior_message=JuniorSharedMessageOut.model_validate(junior_row) if junior_row else None,
        reply_status=reply_status,
        detail=store.REPLY_STUB_DETAIL if junior_row is None else None,
    )


@router.get("/threads", response_model=list[JuniorSharedThreadOut])
def list_threads(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[JuniorSharedThreadOut]:
    return [JuniorSharedThreadOut.model_validate(row) for row in store.list_threads(db, user)]


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


@router.get("/threads/{thread_id}/messages", response_model=list[JuniorSharedMessageOut])
def list_messages(
    thread_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[JuniorSharedMessageOut]:
    return [JuniorSharedMessageOut.model_validate(row) for row in store.list_messages(db, user, thread_id)]


@router.post("/threads/{thread_id}/messages", response_model=JuniorSharedMessagePostOut)
def post_message(
    thread_id: UUID,
    payload: JuniorSharedMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMessagePostOut:
    thread, user_row, junior_row, reply_status = store.post_turn(
        db,
        user,
        thread_id=thread_id,
        content=payload.body,
        venue=payload.venue,
        meta=payload.meta,
        device_label=payload.device_label,
    )
    db.commit()
    db.refresh(user_row)
    if junior_row is not None:
        db.refresh(junior_row)
    return _turn_out(thread.id, user_row, junior_row, reply_status)


@router.post("/messages", response_model=JuniorSharedMessagePostOut)
def post_turn(
    payload: JuniorSharedMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMessagePostOut:
    """Sketch turn: `{ thread_id?, text, venue }`. Missing thread_id uses last open thread."""
    thread, user_row, junior_row, reply_status = store.post_turn(
        db,
        user,
        thread_id=payload.thread_id,
        content=payload.body,
        venue=payload.venue,
        meta=payload.meta,
        device_label=payload.device_label,
    )
    db.commit()
    db.refresh(user_row)
    if junior_row is not None:
        db.refresh(junior_row)
    return _turn_out(thread.id, user_row, junior_row, reply_status)


@router.post("/threads/{thread_id}/continue", response_model=JuniorSharedContinueOut)
def continue_thread(
    thread_id: UUID,
    payload: JuniorSharedContinueIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedContinueOut:
    thread = store.thread_owned(db, user, thread_id)
    user_row = junior_row = None
    reply_status = None
    incoming = payload or JuniorSharedContinueIn()
    body = incoming.body
    if body:
        thread, user_row, junior_row, reply_status = store.post_turn(
            db,
            user,
            thread_id=thread_id,
            content=body,
            venue=incoming.venue,
            meta=incoming.meta,
            device_label=incoming.device_label,
        )
        db.commit()
        db.refresh(thread)
        db.refresh(user_row)
        if junior_row is not None:
            db.refresh(junior_row)
    history = store.list_messages(db, user, thread.id)
    return JuniorSharedContinueOut(
        thread=JuniorSharedThreadOut.model_validate(thread),
        messages=[JuniorSharedMessageOut.model_validate(row) for row in history],
        user_message=JuniorSharedMessageOut.model_validate(user_row) if user_row else None,
        junior_message=JuniorSharedMessageOut.model_validate(junior_row) if junior_row else None,
        reply_status=reply_status,
        detail=store.REPLY_STUB_DETAIL if user_row is not None and junior_row is None else None,
    )


@router.get("/search", response_model=list[JuniorSharedSearchHitOut])
def search_memory(
    q: str = Query(min_length=1, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[JuniorSharedSearchHitOut]:
    return [JuniorSharedSearchHitOut.model_validate(hit) for hit in store.search(db, user, q)]


@router.get("/memories", response_model=list[JuniorSharedMemoryOut])
def list_memories(
    kind: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[JuniorSharedMemoryOut]:
    return [JuniorSharedMemoryOut.model_validate(row) for row in store.list_memories(db, user, kind=kind)]


@router.post("/memories", response_model=JuniorSharedMemoryOut)
def upsert_memory(
    payload: JuniorSharedMemoryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMemoryOut:
    row = store.upsert_memory(
        db,
        user,
        memory_id=payload.id,
        kind=payload.kind,
        content=payload.content,
        source_thread=payload.source_thread,
    )
    db.commit()
    db.refresh(row)
    return JuniorSharedMemoryOut.model_validate(row)


def _context_out(pack: dict) -> JuniorAgentContextOut:
    return JuniorAgentContextOut(
        project=JuniorProjectOut.model_validate(pack["project"]),
        thread_summary=pack.get("thread_summary"),
        recent_messages=[JuniorSharedMessageOut.model_validate(row) for row in pack.get("recent_messages") or []],
        memories=[JuniorSharedMemoryOut.model_validate(row) for row in pack.get("memories") or []],
        search_hits=[JuniorSharedSearchHitOut.model_validate(hit) for hit in pack.get("search_hits") or []],
        launch_hint=str(pack.get("launch_hint") or ""),
    )


@router.get("/projects", response_model=list[JuniorProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[JuniorProjectOut]:
    return [JuniorProjectOut.model_validate(row) for row in store.list_projects(db, user)]


@router.get("/projects/{slug}", response_model=JuniorProjectOut)
def get_project(
    slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorProjectOut:
    return JuniorProjectOut.model_validate(store.get_project(db, user, slug))


@router.post("/projects", response_model=JuniorProjectOut)
def upsert_project(
    payload: JuniorProjectIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorProjectOut:
    row = store.upsert_project(
        db,
        user,
        slug=payload.slug,
        display_name=payload.display_name,
        kind=payload.kind,
        repo_url=payload.repo_url,
        default_branch=payload.default_branch,
        notes=payload.notes,
        meta=payload.meta,
    )
    db.commit()
    db.refresh(row)
    return JuniorProjectOut.model_validate(row)


@router.get("/agent-context", response_model=JuniorAgentContextOut)
def agent_context(
    project: str = Query(min_length=1, max_length=64),
    q: str | None = Query(default=None, max_length=200),
    thread_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentContextOut:
    pack = store.build_agent_context(db, user, project_slug=project, query=q, thread_id=thread_id)
    return _context_out(pack)


@router.post("/agents", response_model=JuniorAgentLaunchOut)
def launch_agent_stub(
    payload: JuniorAgentLaunchIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentLaunchOut:
    """Build an agent-context pack and record the attempt. Does not call Cursor."""
    run, pack = store.record_agent_run(
        db,
        user,
        project_slug=payload.project_slug,
        prompt=payload.prompt,
        thread_id=payload.thread_id,
        query=payload.q,
    )
    db.commit()
    db.refresh(run)
    return JuniorAgentLaunchOut(
        run=JuniorAgentRunOut.model_validate(run),
        context=_context_out(pack),
        called_cursor_api=False,
    )
