from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.schemas import (
    JuniorAgentContextIn,
    JuniorAgentContextOut,
    JuniorAgentLaunchIn,
    JuniorAgentLaunchOut,
    JuniorAgentRunIn,
    JuniorAgentRunOut,
    JuniorDocumentOut,
    JuniorProjectOut,
    JuniorSharedMemoryOut,
    JuniorSharedMessageOut,
    JuniorSharedSearchHitOut,
)
from app.services import junior_shared_memory as store


router = APIRouter(tags=["junior-shared-agents"])


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

@router.get("/agents", response_model=list[JuniorAgentRunOut])
def list_agent_runs(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
    project: str | None = Query(default=None, max_length=64),
) -> list[JuniorAgentRunOut]:
    rows, next_cursor = store.list_agent_runs_page(
        db, user, limit=limit, cursor=cursor, before_id=before_id, project_slug=project
    )
    _page_headers(response, next_cursor)
    return [JuniorAgentRunOut.model_validate(row) for row in rows]


@router.get("/agents/{run_id}", response_model=JuniorAgentRunOut)
def get_agent_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentRunOut:
    return JuniorAgentRunOut.model_validate(store.agent_run_owned(db, user, run_id))


@router.post("/agents/{run_id}", response_model=JuniorAgentRunOut)
def update_agent_run(
    run_id: UUID,
    payload: JuniorAgentRunIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentRunOut:
    fields = payload.model_fields_set
    row = store.update_agent_run(
        db,
        user,
        run_id,
        prompt=payload.prompt,
        status_value=payload.status if "status" in fields else None,
        cursor_agent_id=payload.cursor_agent_id if "cursor_agent_id" in fields else None,
        thread_id=payload.thread_id if "thread_id" in fields else None,
        meta=payload.meta if "meta" in fields else None,
        set_status="status" in fields,
        set_cursor_agent_id="cursor_agent_id" in fields,
        set_thread_id="thread_id" in fields,
        set_meta="meta" in fields,
    )
    db.commit()
    db.refresh(row)
    return JuniorAgentRunOut.model_validate(row)


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


@router.get("/agent-context/{slug}", response_model=JuniorAgentContextOut)
def get_agent_context(
    slug: str,
    q: str | None = Query(default=None, max_length=200),
    thread_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentContextOut:
    pack = store.build_agent_context(db, user, project_slug=slug, query=q, thread_id=thread_id)
    return _context_out(pack)


@router.post("/agent-context/{slug}", response_model=JuniorAgentContextOut)
def update_agent_context(
    slug: str,
    payload: JuniorAgentContextIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentContextOut:
    incoming = payload or JuniorAgentContextIn()
    fields = incoming.model_fields_set
    pack = store.update_agent_context(
        db,
        user,
        slug,
        query=incoming.q if "q" in fields else None,
        thread_id=incoming.thread_id if "thread_id" in fields else None,
        set_query="q" in fields,
        set_thread_id="thread_id" in fields,
    )
    db.commit()
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


