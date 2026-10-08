from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.schemas import (
    JuniorSharedMemoryIn,
    JuniorSharedMemoryOut,
)
from app.services import junior_shared_memory as store


router = APIRouter(tags=["junior-shared-memories"])


def _page_headers(response: Response, next_cursor: str | None) -> None:
    response.headers["X-Has-More"] = "true" if next_cursor else "false"
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor

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


