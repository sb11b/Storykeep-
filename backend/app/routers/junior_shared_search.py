from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.schemas import (
    JuniorSharedSearchHitIn,
    JuniorSharedSearchHitOut,
)
from app.services import junior_shared_memory as store


router = APIRouter(tags=["junior-shared-search"])


def _page_headers(response: Response, next_cursor: str | None) -> None:
    response.headers["X-Has-More"] = "true" if next_cursor else "false"
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor

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


