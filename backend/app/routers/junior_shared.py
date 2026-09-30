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
    JuniorAgentLaunchIn,
    JuniorAgentLaunchOut,
    JuniorProjectAgentLaunchIn,
    JuniorProjectThreadAgentLaunchIn,
    JuniorThreadAgentLaunchIn,
    JuniorAgentRunIn,
    JuniorAgentRunOut,
    JuniorProjectIn,
    JuniorProjectOut,
    JuniorSharedContinueIn,
    JuniorSharedContinueOut,
    JuniorSharedMemoryIn,
    JuniorSharedMemoryOut,
    JuniorSessionIn,
    JuniorSessionOut,
    JuniorSharedMessageIn,
    JuniorSharedMessageOut,
    JuniorSharedMessagePostOut,
    JuniorSharedSearchHitIn,
    JuniorSharedSearchHitOut,
    JuniorProjectSearchIn,
    JuniorProjectThreadSearchIn,
    JuniorThreadSearchIn,
    JuniorSharedThreadIn,
    JuniorSharedThreadOut,
)
from app.services import junior_memory as standing_note
from app.services import junior_shared_memory as store

router = APIRouter(prefix="/junior", tags=["junior-shared-memory"])


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


@router.get("/search", response_model=list[JuniorSharedSearchHitOut])
def search_memory(
    response: Response,
    q: str = Query(min_length=1, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorSharedSearchHitOut]:
    hits, next_cursor = store.search_page(
        db, user, q, limit=limit, cursor=cursor, before_id=before_id
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedSearchHitOut.model_validate(hit) for hit in hits]


@router.get("/search/{message_id}", response_model=JuniorSharedSearchHitOut)
def get_search_hit(
    message_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedSearchHitOut:
    return JuniorSharedSearchHitOut.model_validate(store.search_hit_owned(db, user, message_id))


@router.post("/search/{message_id}", response_model=JuniorSharedSearchHitOut)
def update_search_hit(
    message_id: UUID,
    payload: JuniorSharedSearchHitIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedSearchHitOut:
    incoming = payload or JuniorSharedSearchHitIn()
    fields = incoming.model_fields_set
    hit = store.update_search_hit(
        db,
        user,
        message_id,
        snippet=incoming.snippet if "snippet" in fields else None,
        venue=incoming.venue if "venue" in fields else None,
        set_snippet="snippet" in fields,
        set_venue="venue" in fields,
    )
    db.commit()
    return JuniorSharedSearchHitOut.model_validate(hit)


@router.get("/memories", response_model=list[JuniorSharedMemoryOut])
def list_memories(
    response: Response,
    kind: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorSharedMemoryOut]:
    rows, next_cursor = store.list_memories_page(
        db, user, kind=kind, limit=limit, cursor=cursor, before_id=before_id
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedMemoryOut.model_validate(row) for row in rows]


@router.get("/memories/{memory_id}", response_model=JuniorSharedMemoryOut)
def get_memory(
    memory_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMemoryOut:
    return JuniorSharedMemoryOut.model_validate(store.memory_owned(db, user, memory_id))


@router.post("/memories/{memory_id}", response_model=JuniorSharedMemoryOut)
def update_memory(
    memory_id: UUID,
    payload: JuniorSharedMemoryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMemoryOut:
    fields = payload.model_fields_set
    row = store.update_memory(
        db,
        user,
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
        launch_hint=str(pack.get("launch_hint") or ""),
    )


@router.get("/projects", response_model=list[JuniorProjectOut])
def list_projects(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorProjectOut]:
    rows, next_cursor = store.list_projects_page(
        db, user, limit=limit, cursor=cursor, before_id=before_id
    )
    _page_headers(response, next_cursor)
    return [JuniorProjectOut.model_validate(row) for row in rows]


@router.get("/projects/{slug}", response_model=JuniorProjectOut)
def get_project(
    slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorProjectOut:
    return JuniorProjectOut.model_validate(store.get_project(db, user, slug))


@router.get("/projects/{slug}/agents", response_model=list[JuniorAgentRunOut])
def list_project_agents(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorAgentRunOut]:
    store.get_project(db, user, slug)
    rows, next_cursor = store.list_agent_runs_page(
        db, user, limit=limit, cursor=cursor, before_id=before_id, project_slug=slug
    )
    _page_headers(response, next_cursor)
    return [JuniorAgentRunOut.model_validate(row) for row in rows]


@router.post("/projects/{slug}/agents", response_model=JuniorAgentLaunchOut)
def launch_project_agent(
    slug: str,
    payload: JuniorProjectAgentLaunchIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentLaunchOut:
    """Record a launch on this project. Does not call Cursor. Replay stays on this route."""
    run, pack = store.record_agent_run(
        db,
        user,
        project_slug=slug,
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


@router.get("/projects/{slug}/agents/{run_id}", response_model=JuniorAgentRunOut)
def get_project_agent(
    slug: str,
    run_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentRunOut:
    return JuniorAgentRunOut.model_validate(store.project_agent_owned(db, user, slug, run_id))


@router.post("/projects/{slug}/agents/{run_id}", response_model=JuniorAgentRunOut)
def update_project_agent(
    slug: str,
    run_id: UUID,
    payload: JuniorAgentRunIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentRunOut:
    fields = payload.model_fields_set
    row = store.update_project_agent(
        db,
        user,
        slug,
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


@router.get("/projects/{slug}/search", response_model=list[JuniorSharedSearchHitOut])
def list_project_search(
    slug: str,
    response: Response,
    q: str = Query(min_length=1, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorSharedSearchHitOut]:
    project = store.get_project(db, user, slug)
    hits, next_cursor = store.search_page(
        db,
        user,
        q,
        limit=limit,
        cursor=cursor,
        before_id=before_id,
        thread_ids=store.project_search_thread_ids(db, user, project),
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedSearchHitOut.model_validate(hit) for hit in hits]


@router.post("/projects/{slug}/search", response_model=list[JuniorSharedSearchHitOut])
def search_project(
    slug: str,
    payload: JuniorProjectSearchIn,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorSharedSearchHitOut]:
    """Run a search on this project. Replay stays on this route, not GET /search."""
    project = store.get_project(db, user, slug)
    hits, next_cursor = store.search_page(
        db,
        user,
        payload.q,
        limit=limit,
        cursor=cursor,
        before_id=before_id,
        thread_ids=store.project_search_thread_ids(db, user, project),
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedSearchHitOut.model_validate(hit) for hit in hits]


@router.get("/projects/{slug}/search/{message_id}", response_model=JuniorSharedSearchHitOut)
def get_project_search_hit(
    slug: str,
    message_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedSearchHitOut:
    return JuniorSharedSearchHitOut.model_validate(
        store.project_search_hit_owned(db, user, slug, message_id)
    )


@router.post("/projects/{slug}/search/{message_id}", response_model=JuniorSharedSearchHitOut)
def update_project_search_hit(
    slug: str,
    message_id: UUID,
    payload: JuniorSharedSearchHitIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedSearchHitOut:
    """Update a search hit on this project. Replay stays on this route, not POST /search/{id}."""
    incoming = payload or JuniorSharedSearchHitIn()
    fields = incoming.model_fields_set
    hit = store.update_project_search_hit(
        db,
        user,
        slug,
        message_id,
        snippet=incoming.snippet if "snippet" in fields else None,
        venue=incoming.venue if "venue" in fields else None,
        set_snippet="snippet" in fields,
        set_venue="venue" in fields,
    )
    db.commit()
    return JuniorSharedSearchHitOut.model_validate(hit)


@router.get("/projects/{slug}/agent-context", response_model=JuniorAgentContextOut)
def get_project_agent_context(
    slug: str,
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentContextOut:
    pack = store.project_agent_context(db, user, slug, query=q)
    return _context_out(pack)


@router.post("/projects/{slug}/agent-context", response_model=JuniorAgentContextOut)
def update_project_agent_context(
    slug: str,
    payload: JuniorAgentContextIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentContextOut:
    """Pin this project's context pack. Replay stays on this route, not POST /agent-context/{slug}."""
    incoming = payload or JuniorAgentContextIn()
    fields = incoming.model_fields_set
    pack = store.update_project_agent_context(
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


@router.get("/projects/{slug}/memories", response_model=list[JuniorSharedMemoryOut])
def list_project_memories(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
    kind: str | None = Query(default=None, max_length=24),
) -> list[JuniorSharedMemoryOut]:
    rows, next_cursor = store.list_project_memories_page(
        db,
        user,
        slug,
        kind=kind,
        limit=limit,
        cursor=cursor,
        before_id=before_id,
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedMemoryOut.model_validate(row) for row in rows]


@router.post("/projects/{slug}/memories", response_model=JuniorSharedMemoryOut)
def create_project_memory(
    slug: str,
    payload: JuniorSharedMemoryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMemoryOut:
    """Save a memory on this project. Replay stays on this route, not POST /memories."""
    row = store.create_project_memory(
        db,
        user,
        slug,
        kind=payload.kind,
        content=payload.content,
    )
    db.commit()
    db.refresh(row)
    return JuniorSharedMemoryOut.model_validate(row)


@router.get("/projects/{slug}/memories/{memory_id}", response_model=JuniorSharedMemoryOut)
def get_project_memory(
    slug: str,
    memory_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMemoryOut:
    return JuniorSharedMemoryOut.model_validate(
        store.project_memory_owned(db, user, slug, memory_id)
    )


@router.post("/projects/{slug}/memories/{memory_id}", response_model=JuniorSharedMemoryOut)
def update_project_memory(
    slug: str,
    memory_id: UUID,
    payload: JuniorSharedMemoryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMemoryOut:
    """Update a memory on this project. Replay stays on this route, not POST /memories/{id}."""
    fields = payload.model_fields_set
    row = store.update_project_memory(
        db,
        user,
        slug,
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


@router.get("/projects/{slug}/messages", response_model=list[JuniorSharedMessageOut])
def list_project_messages(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorSharedMessageOut]:
    rows, next_cursor = store.list_project_messages_page(
        db,
        user,
        slug,
        limit=limit,
        cursor=cursor,
        before_id=before_id,
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedMessageOut.model_validate(row) for row in rows]


@router.post("/projects/{slug}/messages", response_model=JuniorSharedMessagePostOut)
def create_project_message(
    slug: str,
    payload: JuniorSharedMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMessagePostOut:
    """Save a message on this project. Replay stays on this route, not POST /messages."""
    thread, user_row, junior_row, reply_status = store.create_project_message(
        db,
        user,
        slug,
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


@router.get("/projects/{slug}/messages/{message_id}", response_model=JuniorSharedMessageOut)
def get_project_message(
    slug: str,
    message_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMessageOut:
    return JuniorSharedMessageOut.model_validate(
        store.project_message_owned(db, user, slug, message_id)
    )


@router.post("/projects/{slug}/messages/{message_id}", response_model=JuniorSharedMessageOut)
def update_project_message(
    slug: str,
    message_id: UUID,
    payload: JuniorSharedMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMessageOut:
    """Update a message on this project. Replay stays on this route, not POST /messages/{id}."""
    fields = payload.model_fields_set
    row = store.update_project_message(
        db,
        user,
        slug,
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


@router.get("/projects/{slug}/continue", response_model=JuniorSharedContinueOut)
def get_project_continue(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> JuniorSharedContinueOut:
    """Continue history for this project's pinned thread. 404 if the project or thread is missing."""
    thread = store.project_continue_thread(db, user, slug)
    history, next_cursor = store.list_messages_page(
        db, user, thread.id, limit=limit, cursor=cursor, before_id=before_id
    )
    _page_headers(response, next_cursor)
    return JuniorSharedContinueOut(
        thread=JuniorSharedThreadOut.model_validate(thread),
        messages=[JuniorSharedMessageOut.model_validate(row) for row in history],
    )


@router.post("/projects/{slug}/continue", response_model=JuniorSharedContinueOut)
def continue_project(
    slug: str,
    response: Response,
    payload: JuniorSharedContinueIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> JuniorSharedContinueOut:
    """Resume this project's pinned thread. Replay stays on this route, not POST /threads/{id}/continue."""
    thread = store.project_continue_thread(db, user, slug)
    user_row = junior_row = None
    reply_status = None
    incoming = payload or JuniorSharedContinueIn()
    body = incoming.body
    if body:
        thread, user_row, junior_row, reply_status = store.post_turn(
            db,
            user,
            thread_id=thread.id,
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


@router.get("/projects/{slug}/threads", response_model=list[JuniorSharedThreadOut])
def list_project_threads(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorSharedThreadOut]:
    rows, next_cursor = store.list_project_threads_page(
        db,
        user,
        slug,
        limit=limit,
        cursor=cursor,
        before_id=before_id,
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedThreadOut.model_validate(row) for row in rows]


@router.post("/projects/{slug}/threads")
def create_project_thread(
    slug: str,
    payload: JuniorSharedThreadIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedThreadOut | JuniorSharedMessagePostOut:
    """Open a thread on this project. Replay stays on this route, not POST /threads."""
    row = store.create_project_thread(
        db,
        user,
        slug,
        title=payload.title,
        venue=payload.venue,
        status_value=payload.status,
    )
    first = (payload.content or payload.text or "").strip()
    if first:
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
    db.commit()
    db.refresh(row)
    return JuniorSharedThreadOut.model_validate(row)


@router.get(
    "/projects/{slug}/threads/{thread_id}/messages",
    response_model=list[JuniorSharedMessageOut],
)
def list_project_thread_messages(
    slug: str,
    thread_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorSharedMessageOut]:
    """Messages on one thread of this project. 404 if the thread is not on the project."""
    rows, next_cursor = store.list_project_thread_messages_page(
        db,
        user,
        slug,
        thread_id,
        limit=limit,
        cursor=cursor,
        before_id=before_id,
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedMessageOut.model_validate(row) for row in rows]


@router.post(
    "/projects/{slug}/threads/{thread_id}/messages",
    response_model=JuniorSharedMessagePostOut,
)
def create_project_thread_message(
    slug: str,
    thread_id: UUID,
    payload: JuniorSharedMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMessagePostOut:
    """Save a message on this project thread. Replay stays on this route."""
    thread, user_row, junior_row, reply_status = store.create_project_thread_message(
        db,
        user,
        slug,
        thread_id,
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


@router.get(
    "/projects/{slug}/threads/{thread_id}/messages/{message_id}",
    response_model=JuniorSharedMessageOut,
)
def get_project_thread_message(
    slug: str,
    thread_id: UUID,
    message_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMessageOut:
    """One message on a thread of this project. 404 if the thread or message is not on it."""
    return JuniorSharedMessageOut.model_validate(
        store.project_thread_message_owned(db, user, slug, thread_id, message_id)
    )


@router.post(
    "/projects/{slug}/threads/{thread_id}/messages/{message_id}",
    response_model=JuniorSharedMessageOut,
)
def update_project_thread_message(
    slug: str,
    thread_id: UUID,
    message_id: UUID,
    payload: JuniorSharedMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMessageOut:
    """Update a message on this project thread. Replay stays on this route."""
    fields = payload.model_fields_set
    row = store.update_project_thread_message(
        db,
        user,
        slug,
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


@router.get(
    "/projects/{slug}/threads/{thread_id}/continue",
    response_model=JuniorSharedContinueOut,
)
def get_project_thread_continue(
    slug: str,
    thread_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> JuniorSharedContinueOut:
    """Continue history for one thread on this project. 404 if the thread is not on the project."""
    thread = store.project_thread_owned(db, user, slug, thread_id)
    history, next_cursor = store.list_messages_page(
        db, user, thread.id, limit=limit, cursor=cursor, before_id=before_id
    )
    _page_headers(response, next_cursor)
    return JuniorSharedContinueOut(
        thread=JuniorSharedThreadOut.model_validate(thread),
        messages=[JuniorSharedMessageOut.model_validate(row) for row in history],
    )


@router.post(
    "/projects/{slug}/threads/{thread_id}/continue",
    response_model=JuniorSharedContinueOut,
)
def continue_project_thread(
    slug: str,
    thread_id: UUID,
    response: Response,
    payload: JuniorSharedContinueIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> JuniorSharedContinueOut:
    """Resume this project thread. Replay stays on this route, not POST /projects/{slug}/continue."""
    thread = store.project_thread_owned(db, user, slug, thread_id)
    user_row = junior_row = None
    reply_status = None
    incoming = payload or JuniorSharedContinueIn()
    body = incoming.body
    if body:
        thread, user_row, junior_row, reply_status = store.continue_project_thread(
            db,
            user,
            slug,
            thread_id,
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


@router.get(
    "/projects/{slug}/threads/{thread_id}/memories",
    response_model=list[JuniorSharedMemoryOut],
)
def list_project_thread_memories(
    slug: str,
    thread_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
    kind: str | None = Query(default=None, max_length=24),
) -> list[JuniorSharedMemoryOut]:
    """Memories sourced from one thread on this project. 404 if the thread is not on the project."""
    rows, next_cursor = store.list_project_thread_memories_page(
        db,
        user,
        slug,
        thread_id,
        kind=kind,
        limit=limit,
        cursor=cursor,
        before_id=before_id,
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedMemoryOut.model_validate(row) for row in rows]


@router.post(
    "/projects/{slug}/threads/{thread_id}/memories",
    response_model=JuniorSharedMemoryOut,
)
def create_project_thread_memory(
    slug: str,
    thread_id: UUID,
    payload: JuniorSharedMemoryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMemoryOut:
    """Save a memory on this project thread. Replay stays on this route."""
    row = store.create_project_thread_memory(
        db,
        user,
        slug,
        thread_id,
        kind=payload.kind,
        content=payload.content,
    )
    db.commit()
    db.refresh(row)
    return JuniorSharedMemoryOut.model_validate(row)


@router.get(
    "/projects/{slug}/threads/{thread_id}/memories/{memory_id}",
    response_model=JuniorSharedMemoryOut,
)
def get_project_thread_memory(
    slug: str,
    thread_id: UUID,
    memory_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMemoryOut:
    """One memory sourced from a thread on this project. 404 if it is not on that thread."""
    return JuniorSharedMemoryOut.model_validate(
        store.project_thread_memory_owned(db, user, slug, thread_id, memory_id)
    )


@router.post(
    "/projects/{slug}/threads/{thread_id}/memories/{memory_id}",
    response_model=JuniorSharedMemoryOut,
)
def update_project_thread_memory(
    slug: str,
    thread_id: UUID,
    memory_id: UUID,
    payload: JuniorSharedMemoryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedMemoryOut:
    """Update a memory on this project thread. Replay stays on this route."""
    fields = payload.model_fields_set
    row = store.update_project_thread_memory(
        db,
        user,
        slug,
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


@router.get(
    "/projects/{slug}/threads/{thread_id}/agents",
    response_model=list[JuniorAgentRunOut],
)
def list_project_thread_agents(
    slug: str,
    thread_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorAgentRunOut]:
    """Agent runs on one thread of this project. 404 if the thread is not on the project."""
    rows, next_cursor = store.list_project_thread_agents_page(
        db,
        user,
        slug,
        thread_id,
        limit=limit,
        cursor=cursor,
        before_id=before_id,
    )
    _page_headers(response, next_cursor)
    return [JuniorAgentRunOut.model_validate(row) for row in rows]


@router.post(
    "/projects/{slug}/threads/{thread_id}/agents",
    response_model=JuniorAgentLaunchOut,
)
def launch_project_thread_agent(
    slug: str,
    thread_id: UUID,
    payload: JuniorProjectThreadAgentLaunchIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentLaunchOut:
    """Record a launch on this project thread. Does not call Cursor. Replay stays on this route."""
    run, pack = store.create_project_thread_agent(
        db,
        user,
        slug,
        thread_id,
        prompt=payload.prompt,
        query=payload.q,
    )
    db.commit()
    db.refresh(run)
    return JuniorAgentLaunchOut(
        run=JuniorAgentRunOut.model_validate(run),
        context=_context_out(pack),
        called_cursor_api=False,
    )


@router.get(
    "/projects/{slug}/threads/{thread_id}/agents/{run_id}",
    response_model=JuniorAgentRunOut,
)
def get_project_thread_agent(
    slug: str,
    thread_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentRunOut:
    """One agent run on a thread of this project. 404 if the run is not on that thread."""
    return JuniorAgentRunOut.model_validate(
        store.project_thread_agent_owned(db, user, slug, thread_id, run_id)
    )


@router.post(
    "/projects/{slug}/threads/{thread_id}/agents/{run_id}",
    response_model=JuniorAgentRunOut,
)
def update_project_thread_agent(
    slug: str,
    thread_id: UUID,
    run_id: UUID,
    payload: JuniorAgentRunIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentRunOut:
    """Update an agent run on this project thread. Replay stays on this route."""
    fields = payload.model_fields_set
    row = store.update_project_thread_agent(
        db,
        user,
        slug,
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


@router.get(
    "/projects/{slug}/threads/{thread_id}/sessions",
    response_model=list[JuniorSessionOut],
)
def list_project_thread_sessions(
    slug: str,
    thread_id: UUID,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorSessionOut]:
    """Sessions on this project thread (venue matches the thread). 404 if the thread is not on the project."""
    rows, next_cursor = store.list_project_thread_sessions_page(
        db, user, slug, thread_id, limit=limit, cursor=cursor, before_id=before_id
    )
    _page_headers(response, next_cursor)
    return [JuniorSessionOut.model_validate(row) for row in rows]


@router.post(
    "/projects/{slug}/threads/{thread_id}/sessions",
    response_model=JuniorSessionOut,
)
def heartbeat_project_thread_session(
    slug: str,
    thread_id: UUID,
    payload: JuniorSessionIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSessionOut:
    """Heartbeat a session on this project thread. Replay stays on this route, not POST /threads/{id}/sessions."""
    incoming = payload or JuniorSessionIn()
    fields = incoming.model_fields_set
    row = store.touch_project_thread_session(
        db,
        user,
        slug,
        thread_id,
        venue=incoming.venue if "venue" in fields else None,
        device_label=incoming.device_label if "device_label" in fields else None,
    )
    db.commit()
    db.refresh(row)
    return JuniorSessionOut.model_validate(row)


@router.get(
    "/projects/{slug}/threads/{thread_id}/sessions/{session_id}",
    response_model=JuniorSessionOut,
)
def get_project_thread_session(
    slug: str,
    thread_id: UUID,
    session_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSessionOut:
    """One session on a thread of this project. 404 if the thread is not on the project or the venue does not match."""
    return JuniorSessionOut.model_validate(
        store.project_thread_session_owned(db, user, slug, thread_id, session_id)
    )


@router.post(
    "/projects/{slug}/threads/{thread_id}/sessions/{session_id}",
    response_model=JuniorSessionOut,
)
def update_project_thread_session(
    slug: str,
    thread_id: UUID,
    session_id: UUID,
    payload: JuniorSessionIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSessionOut:
    """Update a session on this project thread. Replay stays on this route, not POST /threads/{id}/sessions/{id}."""
    incoming = payload or JuniorSessionIn()
    fields = incoming.model_fields_set
    row = store.update_project_thread_session(
        db,
        user,
        slug,
        thread_id,
        session_id,
        venue=incoming.venue if "venue" in fields else None,
        device_label=incoming.device_label if "device_label" in fields else None,
        set_device_label="device_label" in fields,
    )
    db.commit()
    db.refresh(row)
    return JuniorSessionOut.model_validate(row)


@router.get(
    "/projects/{slug}/sessions",
    response_model=list[JuniorSessionOut],
)
def list_project_sessions(
    slug: str,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorSessionOut]:
    """Sessions whose venue matches a thread tied to this project. 404 if the project is missing."""
    rows, next_cursor = store.list_project_sessions_page(
        db, user, slug, limit=limit, cursor=cursor, before_id=before_id
    )
    _page_headers(response, next_cursor)
    return [JuniorSessionOut.model_validate(row) for row in rows]


@router.post(
    "/projects/{slug}/sessions",
    response_model=JuniorSessionOut,
)
def heartbeat_project_session(
    slug: str,
    payload: JuniorSessionIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSessionOut:
    """Heartbeat a session on this project. Replay stays on this route, not POST /sessions."""
    incoming = payload or JuniorSessionIn()
    fields = incoming.model_fields_set
    row = store.touch_project_session(
        db,
        user,
        slug,
        venue=incoming.venue if "venue" in fields else None,
        device_label=incoming.device_label if "device_label" in fields else None,
    )
    db.commit()
    db.refresh(row)
    return JuniorSessionOut.model_validate(row)


@router.get(
    "/projects/{slug}/sessions/{session_id}",
    response_model=JuniorSessionOut,
)
def get_project_session(
    slug: str,
    session_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSessionOut:
    """One session on this project. Venue must match a thread tied to the project."""
    return JuniorSessionOut.model_validate(store.project_session_owned(db, user, slug, session_id))


@router.post(
    "/projects/{slug}/sessions/{session_id}",
    response_model=JuniorSessionOut,
)
def update_project_session(
    slug: str,
    session_id: UUID,
    payload: JuniorSessionIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSessionOut:
    """Update a session on this project. Replay stays on this route, not POST /sessions/{id}."""
    incoming = payload or JuniorSessionIn()
    fields = incoming.model_fields_set
    row = store.update_project_session(
        db,
        user,
        slug,
        session_id,
        venue=incoming.venue if "venue" in fields else None,
        device_label=incoming.device_label if "device_label" in fields else None,
        set_device_label="device_label" in fields,
    )
    db.commit()
    db.refresh(row)
    return JuniorSessionOut.model_validate(row)


@router.get(
    "/projects/{slug}/threads/{thread_id}/search",
    response_model=list[JuniorSharedSearchHitOut],
)
def list_project_thread_search(
    slug: str,
    thread_id: UUID,
    response: Response,
    q: str = Query(min_length=1, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorSharedSearchHitOut]:
    """Search hits on one thread of this project. 404 if the thread is not on the project."""
    hits, next_cursor = store.search_project_thread(
        db,
        user,
        slug,
        thread_id,
        q,
        limit=limit,
        cursor=cursor,
        before_id=before_id,
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedSearchHitOut.model_validate(hit) for hit in hits]


@router.post(
    "/projects/{slug}/threads/{thread_id}/search",
    response_model=list[JuniorSharedSearchHitOut],
)
def search_project_thread(
    slug: str,
    thread_id: UUID,
    payload: JuniorProjectThreadSearchIn,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorSharedSearchHitOut]:
    """Run a search on this project thread. Replay stays on this route."""
    hits, next_cursor = store.search_project_thread(
        db,
        user,
        slug,
        thread_id,
        payload.q,
        limit=limit,
        cursor=cursor,
        before_id=before_id,
    )
    _page_headers(response, next_cursor)
    return [JuniorSharedSearchHitOut.model_validate(hit) for hit in hits]


@router.get(
    "/projects/{slug}/threads/{thread_id}/search/{message_id}",
    response_model=JuniorSharedSearchHitOut,
)
def get_project_thread_search_hit(
    slug: str,
    thread_id: UUID,
    message_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedSearchHitOut:
    """One search hit on a thread of this project. 404 if the hit is not on that thread."""
    return JuniorSharedSearchHitOut.model_validate(
        store.project_thread_search_hit_owned(db, user, slug, thread_id, message_id)
    )


@router.post(
    "/projects/{slug}/threads/{thread_id}/search/{message_id}",
    response_model=JuniorSharedSearchHitOut,
)
def update_project_thread_search_hit(
    slug: str,
    thread_id: UUID,
    message_id: UUID,
    payload: JuniorSharedSearchHitIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedSearchHitOut:
    """Update a search hit on this project thread. Replay stays on this route."""
    incoming = payload or JuniorSharedSearchHitIn()
    fields = incoming.model_fields_set
    hit = store.update_project_thread_search_hit(
        db,
        user,
        slug,
        thread_id,
        message_id,
        snippet=incoming.snippet if "snippet" in fields else None,
        venue=incoming.venue if "venue" in fields else None,
        set_snippet="snippet" in fields,
        set_venue="venue" in fields,
    )
    db.commit()
    return JuniorSharedSearchHitOut.model_validate(hit)


@router.get(
    "/projects/{slug}/threads/{thread_id}/agent-context",
    response_model=JuniorAgentContextOut,
)
def get_project_thread_agent_context(
    slug: str,
    thread_id: UUID,
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentContextOut:
    """Context pack for one thread on this project. 404 if the thread is not on the project."""
    pack = store.project_thread_agent_context(db, user, slug, thread_id, query=q)
    return _context_out(pack)


@router.post(
    "/projects/{slug}/threads/{thread_id}/agent-context",
    response_model=JuniorAgentContextOut,
)
def update_project_thread_agent_context(
    slug: str,
    thread_id: UUID,
    payload: JuniorAgentContextIn | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorAgentContextOut:
    """Pin this project thread's context pack. Replay stays on this route."""
    incoming = payload or JuniorAgentContextIn()
    fields = incoming.model_fields_set
    pack = store.update_project_thread_agent_context(
        db,
        user,
        slug,
        thread_id,
        query=incoming.q if "q" in fields else None,
        thread_id_value=incoming.thread_id if "thread_id" in fields else None,
        set_query="q" in fields,
        set_thread_id="thread_id" in fields,
    )
    db.commit()
    return _context_out(pack)


@router.get("/projects/{slug}/threads/{thread_id}", response_model=JuniorSharedThreadOut)
def get_project_thread(
    slug: str,
    thread_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedThreadOut:
    return JuniorSharedThreadOut.model_validate(store.project_thread_owned(db, user, slug, thread_id))


@router.post("/projects/{slug}/threads/{thread_id}", response_model=JuniorSharedThreadOut)
def update_project_thread(
    slug: str,
    thread_id: UUID,
    payload: JuniorSharedThreadIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorSharedThreadOut:
    """Update a thread on this project. Replay stays on this route, not POST /threads/{id}."""
    row = store.update_project_thread(
        db,
        user,
        slug,
        thread_id,
        title=payload.title if "title" in payload.model_fields_set else None,
        status_value=payload.status if "status" in payload.model_fields_set else None,
    )
    db.commit()
    db.refresh(row)
    return JuniorSharedThreadOut.model_validate(row)


@router.post("/projects/{slug}", response_model=JuniorProjectOut)
def update_project(
    slug: str,
    payload: JuniorProjectIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorProjectOut:
    fields = payload.model_fields_set
    row = store.update_project(
        db,
        user,
        slug,
        display_name=payload.display_name if "display_name" in fields else None,
        kind=payload.kind if "kind" in fields else None,
        repo_url=payload.repo_url if "repo_url" in fields else None,
        default_branch=payload.default_branch if "default_branch" in fields else None,
        notes=payload.notes if "notes" in fields else None,
        meta=payload.meta if "meta" in fields else None,
    )
    db.commit()
    db.refresh(row)
    return JuniorProjectOut.model_validate(row)


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
