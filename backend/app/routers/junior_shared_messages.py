from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.schemas import (
    JuniorAgentContextIn,
    JuniorAgentContextOut,
    JuniorAgentLaunchOut,
    JuniorThreadAgentLaunchIn,
    JuniorAgentRunIn,
    JuniorAgentRunOut,
    JuniorDocumentOut,
    JuniorProjectOut,
    JuniorSharedContinueIn,
    JuniorSharedContinueOut,
    JuniorSharedMemoryIn,
    JuniorSharedMemoryOut,
    JuniorSharedMessageIn,
    JuniorSharedMessageOut,
    JuniorSharedMessagePostOut,
    JuniorSharedSearchHitIn,
    JuniorSharedSearchHitOut,
    JuniorThreadSearchIn,
    JuniorSharedThreadOut,
)
from app.services import junior_memory as standing_note
from app.services import junior_shared_memory as store


router = APIRouter(tags=["junior-shared-messages"])


class JuniorThreadMemoryNoteIn(BaseModel):
    text: str = Field(default="", max_length=standing_note.MEMORY_SAVE_CHARS)


def _standing_note_payload(row) -> dict:
    updated = getattr(row, "updated_at", None) if row is not None else None
    markdown = ""
    if row is not None:
        markdown = (getattr(row, "markdown", None) or "") or ""
    return {
        "markdown": markdown,
        "updated_at": updated.isoformat() if updated else None,
    }


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


@router.get("/messages/{message_id}", response_model=JuniorSharedMessageOut)
def get_message(
    message_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMessageOut:
    return JuniorSharedMessageOut.model_validate(store.message_owned(db, user, message_id))


@router.post("/messages/{message_id}", response_model=JuniorSharedMessageOut)
def update_message(
    message_id: UUID,
    payload: JuniorSharedMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMessageOut:
    fields = payload.model_fields_set
    row = store.update_message(
        db,
        user,
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


@router.get("/messages", response_model=list[JuniorSharedMessageOut])
def list_recent_messages(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
    thread_id: UUID | None = Query(default=None),
) -> list[JuniorSharedMessageOut]:
    rows, next_cursor = store.list_recent_messages_page(
        db, user, limit=limit, cursor=cursor, before_id=before_id, thread_id=thread_id
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedMessageOut.model_validate(row) for row in rows]


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


@router.get("/projects/{slug}/threads/{thread_id}/memory")
def get_project_thread_memory_note(
    slug: str,
    thread_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    """Standing note when this thread is on the project. 404 if the project or thread is missing."""
    store.project_thread_owned(db, user, slug, thread_id)
    return _standing_note_payload(standing_note.get_row(db, user.id))


@router.post("/projects/{slug}/threads/{thread_id}/memory")
def append_project_thread_memory_note(
    slug: str,
    thread_id: UUID,
    payload: JuniorThreadMemoryNoteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    """Append to the standing note for a thread on this project. The original text stays."""
    store.project_thread_owned(db, user, slug, thread_id)
    row = standing_note.append_markdown(db, user, payload.text)
    db.commit()
    return _standing_note_payload(row)


@router.get("/threads/{thread_id}/memory")
def get_thread_memory_note(
    thread_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    """Standing note for the owner of this thread. 404 if the thread is missing."""
    store.thread_owned(db, user, thread_id)
    return _standing_note_payload(standing_note.get_row(db, user.id))


@router.post("/threads/{thread_id}/memory")
def append_thread_memory_note(
    thread_id: UUID,
    payload: JuniorThreadMemoryNoteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> dict:
    """Append to the standing note. The original text stays. Replay stays on this route, not POST /memory."""
    store.thread_owned(db, user, thread_id)
    row = standing_note.append_markdown(db, user, payload.text)
    db.commit()
    return _standing_note_payload(row)


@router.get("/threads/{thread_id}/memories", response_model=list[JuniorSharedMemoryOut])
def list_thread_memories(
    thread_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
    kind: str | None = Query(default=None, max_length=24),
) -> list[JuniorSharedMemoryOut]:
    store.thread_owned(db, user, thread_id)
    rows, next_cursor = store.list_memories_page(
        db,
        user,
        kind=kind,
        source_thread=thread_id,
        limit=limit,
        cursor=cursor,
        before_id=before_id,
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedMemoryOut.model_validate(row) for row in rows]


@router.post("/threads/{thread_id}/memories", response_model=JuniorSharedMemoryOut)
def create_thread_memory(
    thread_id: UUID,
    payload: JuniorSharedMemoryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMemoryOut:
    """Save a memory on this thread. Replay stays on this route, not POST /memories."""
    row = store.create_thread_memory(
        db,
        user,
        thread_id,
        kind=payload.kind,
        content=payload.content,
    )
    db.commit()
    db.refresh(row)
    return JuniorSharedMemoryOut.model_validate(row)


@router.get("/threads/{thread_id}/memories/{memory_id}", response_model=JuniorSharedMemoryOut)
def get_thread_memory(
    thread_id: UUID,
    memory_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMemoryOut:
    return JuniorSharedMemoryOut.model_validate(
        store.thread_memory_owned(db, user, thread_id, memory_id)
    )


@router.post("/threads/{thread_id}/memories/{memory_id}", response_model=JuniorSharedMemoryOut)
def update_thread_memory(
    thread_id: UUID,
    memory_id: UUID,
    payload: JuniorSharedMemoryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMemoryOut:
    fields = payload.model_fields_set
    row = store.update_thread_memory(
        db,
        user,
        thread_id,
        memory_id,
        content=payload.content if "content" in fields else None,
        kind=payload.kind if "kind" in fields else None,
        source_thread=payload.source_thread if "source_thread" in fields else None,
        set_kind="kind" in fields,
        set_source_thread="source_thread" in fields,
    )
    db.commit()
    db.refresh(row)
    return JuniorSharedMemoryOut.model_validate(row)


@router.get("/threads/{thread_id}/agents", response_model=list[JuniorAgentRunOut])
def list_thread_agents(
    thread_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorAgentRunOut]:
    store.thread_owned(db, user, thread_id)
    rows, next_cursor = store.list_agent_runs_page(
        db, user, limit=limit, cursor=cursor, before_id=before_id, thread_id=thread_id
    )
    _page_headers(response, next_cursor)
    return [JuniorAgentRunOut.model_validate(row) for row in rows]


@router.post("/threads/{thread_id}/agents", response_model=JuniorAgentLaunchOut)
def launch_thread_agent(
    thread_id: UUID,
    payload: JuniorThreadAgentLaunchIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentLaunchOut:
    """Record a launch on this thread. Does not call Cursor. Replay stays on this route."""
    store.thread_owned(db, user, thread_id)
    run, pack = store.record_agent_run(
        db,
        user,
        project_slug=payload.project_slug,
        prompt=payload.prompt,
        thread_id=thread_id,
        query=payload.q,
    )
    db.commit()
    db.refresh(run)
    return JuniorAgentLaunchOut(
        run=JuniorAgentRunOut.model_validate(run),
        context=_context_out(pack),
        called_cursor_api=False,
    )


@router.get("/threads/{thread_id}/agents/{run_id}", response_model=JuniorAgentRunOut)
def get_thread_agent(
    thread_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentRunOut:
    return JuniorAgentRunOut.model_validate(
        store.thread_agent_owned(db, user, thread_id, run_id)
    )


@router.post("/threads/{thread_id}/agents/{run_id}", response_model=JuniorAgentRunOut)
def update_thread_agent(
    thread_id: UUID,
    run_id: UUID,
    payload: JuniorAgentRunIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentRunOut:
    """Update an agent run on this thread. Replay stays on this route, not POST /agents/{id}."""
    fields = payload.model_fields_set
    row = store.update_thread_agent(
        db,
        user,
        thread_id,
        run_id,
        prompt=payload.prompt,
        status_value=payload.status if "status" in fields else None,
        cursor_agent_id=payload.cursor_agent_id if "cursor_agent_id" in fields else None,
        thread_id_value=payload.thread_id if "thread_id" in fields else None,
        meta=payload.meta if "meta" in fields else None,
        set_status="status" in fields,
        set_cursor_agent_id="cursor_agent_id" in fields,
        set_thread_id="thread_id" in fields,
        set_meta="meta" in fields,
    )
    db.commit()
    db.refresh(row)
    return JuniorAgentRunOut.model_validate(row)


@router.get("/threads/{thread_id}/search", response_model=list[JuniorSharedSearchHitOut])
def list_thread_search(
    thread_id: UUID,
    response: Response,
    q: str = Query(min_length=1, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorSharedSearchHitOut]:
    store.thread_owned(db, user, thread_id)
    hits, next_cursor = store.search_page(
        db, user, q, limit=limit, cursor=cursor, before_id=before_id, thread_id=thread_id
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedSearchHitOut.model_validate(hit) for hit in hits]


@router.post("/threads/{thread_id}/search", response_model=list[JuniorSharedSearchHitOut])
def search_thread(
    thread_id: UUID,
    payload: JuniorThreadSearchIn,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorSharedSearchHitOut]:
    """Run a search on this thread. Replay stays on this route, not GET /search."""
    store.thread_owned(db, user, thread_id)
    hits, next_cursor = store.search_page(
        db,
        user,
        payload.q,
        limit=limit,
        cursor=cursor,
        before_id=before_id,
        thread_id=thread_id,
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedSearchHitOut.model_validate(hit) for hit in hits]


@router.get("/threads/{thread_id}/agent-context/{slug}", response_model=JuniorAgentContextOut)
def get_thread_agent_context(
    thread_id: UUID,
    slug: str,
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentContextOut:
    pack = store.thread_agent_context(db, user, thread_id, slug, query=q)
    return _context_out(pack)


@router.post("/threads/{thread_id}/agent-context/{slug}", response_model=JuniorAgentContextOut)
def update_thread_agent_context(
    thread_id: UUID,
    slug: str,
    payload: JuniorAgentContextIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentContextOut:
    """Pin this thread's context pack. Replay stays on this route, not POST /agent-context/{slug}."""
    incoming = payload or JuniorAgentContextIn()
    fields = incoming.model_fields_set
    pack = store.update_thread_agent_context(
        db,
        user,
        thread_id,
        slug,
        query=incoming.q if "q" in fields else None,
        thread_id_value=incoming.thread_id if "thread_id" in fields else None,
        set_query="q" in fields,
        set_thread_id="thread_id" in fields,
    )
    db.commit()
    return _context_out(pack)


@router.get("/threads/{thread_id}/search/{message_id}", response_model=JuniorSharedSearchHitOut)
def get_thread_search_hit(
    thread_id: UUID,
    message_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedSearchHitOut:
    return JuniorSharedSearchHitOut.model_validate(
        store.thread_search_hit_owned(db, user, thread_id, message_id)
    )


@router.post("/threads/{thread_id}/search/{message_id}", response_model=JuniorSharedSearchHitOut)
def update_thread_search_hit(
    thread_id: UUID,
    message_id: UUID,
    payload: JuniorSharedSearchHitIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedSearchHitOut:
    """Update a search hit on this thread. Replay stays on this route, not POST /search/{id}."""
    incoming = payload or JuniorSharedSearchHitIn()
    fields = incoming.model_fields_set
    hit = store.update_thread_search_hit(
        db,
        user,
        thread_id,
        message_id,
        snippet=incoming.snippet if "snippet" in fields else None,
        venue=incoming.venue if "venue" in fields else None,
        set_snippet="snippet" in fields,
        set_venue="venue" in fields,
    )
    db.commit()
    return JuniorSharedSearchHitOut.model_validate(hit)


@router.get("/threads/{thread_id}/continue", response_model=JuniorSharedContinueOut)
def get_continue_history(
    thread_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> JuniorSharedContinueOut:
    thread = store.thread_owned(db, user, thread_id)
    history, next_cursor = store.list_messages_page(
        db, user, thread.id, limit=limit, cursor=cursor, before_id=before_id
    )
    _page_headers(response, next_cursor)
    return JuniorSharedContinueOut(
        thread=JuniorSharedThreadOut.model_validate(thread),
        messages=[JuniorSharedMessageOut.model_validate(row) for row in history],
    )


@router.post("/threads/{thread_id}/continue", response_model=JuniorSharedContinueOut)
def continue_thread(
    thread_id: UUID,
    response: Response,
    payload: JuniorSharedContinueIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
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
    history, next_cursor = store.list_messages_page(
        db, user, thread.id, limit=limit, cursor=cursor, before_id=before_id
    )
    _page_headers(response, next_cursor)
    return JuniorSharedContinueOut(
        thread=JuniorSharedThreadOut.model_validate(thread),
        messages=[JuniorSharedMessageOut.model_validate(row) for row in history],
        user_message=JuniorSharedMessageOut.model_validate(user_row) if user_row else None,
        junior_message=JuniorSharedMessageOut.model_validate(junior_row) if junior_row else None,
        reply_status=reply_status,
        detail=store.REPLY_STUB_DETAIL if user_row is not None and junior_row is None else None,
    )


