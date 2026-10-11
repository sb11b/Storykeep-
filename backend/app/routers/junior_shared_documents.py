from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.schemas import (
    JuniorDocumentIn,
    JuniorDocumentOut,
)
from app.services import junior_shared_memory as store
from app.services.event_bus import bus


router = APIRouter(tags=["junior-shared-documents"])


def _page_headers(response: Response, next_cursor: str | None) -> None:
    response.headers["X-Has-More"] = "true" if next_cursor else "false"
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor

# ── Documents ───────────────────────────────────────────────────────────────


@router.get("/documents", response_model=list[JuniorDocumentOut])
def list_documents(
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=64),
    before_id: UUID | None = Query(default=None),
) -> list[JuniorDocumentOut]:
    rows, next_cursor = store.list_documents_page(
        db, user, limit=limit, cursor=cursor, before_id=before_id
    )
    _page_headers(response, next_cursor)
    return [JuniorDocumentOut.model_validate(row) for row in rows]


@router.post("/documents", response_model=JuniorDocumentOut)
def create_or_update_document(
    payload: JuniorDocumentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorDocumentOut:
    fields = payload.model_fields_set
    row = store.upsert_document(
        db,
        user,
        slug=payload.slug,
        title=payload.title,
        text=payload.text if "text" in fields else None,
        summary=payload.summary if "summary" in fields else None,
        set_text="text" in fields,
        set_summary="summary" in fields,
    )
    db.commit()
    db.refresh(row)
    # Fresh insert sets created_at == updated_at in the same commit; that
    # distinguishes document.created from document.updated.
    bus.emit(
        user.id,
        {
            "type": "document.created" if row.created_at == row.updated_at else "document.updated",
            "ts": datetime.now(timezone.utc).isoformat(),
            "slug": row.slug,
            "title": row.title,
            "changed": sorted(fields),
            "source": "api",
        },
    )
    return JuniorDocumentOut.model_validate(row)


@router.get("/documents/{slug}", response_model=JuniorDocumentOut)
def get_document(
    slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorDocumentOut:
    return JuniorDocumentOut.model_validate(store.document_owned(db, user, slug))


@router.delete("/documents/{slug}")
def delete_document(
    slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> None:
    store.delete_document(db, user, slug)
    db.commit()
    bus.emit(
        user.id,
        {
            "type": "document.deleted",
            "ts": datetime.now(timezone.utc).isoformat(),
            "slug": slug,
            "source": "api",
        },
    )
