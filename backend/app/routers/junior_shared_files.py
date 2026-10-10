from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import JuniorDocumentFile, User
from app.schemas import JuniorDocumentFileOut
from app.services import junior_shared_files
from app.services.junior_shared_common import normalize_slug

router = APIRouter(tags=["junior-shared-files"])


def _row_for_slug(db: Session, user: User, slug: str, file_id: uuid.UUID) -> JuniorDocumentFile:
    slug_norm = normalize_slug(slug)
    row = db.get(JuniorDocumentFile, file_id)
    if row is None or row.user_id != user.id or row.document_slug != slug_norm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return row


@router.post("/documents/{slug}/files", response_model=JuniorDocumentFileOut)
async def upload_document_file(
    slug: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorDocumentFileOut:
    payload = await file.read()
    row = junior_shared_files.save_file(
        db,
        user,
        slug,
        file.filename or "file",
        payload,
        file.content_type,
    )
    return JuniorDocumentFileOut.model_validate(row)


@router.get("/documents/{slug}/files", response_model=list[JuniorDocumentFileOut])
def list_document_files(
    slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[JuniorDocumentFileOut]:
    rows = junior_shared_files.list_files(db, user, slug)
    return [JuniorDocumentFileOut.model_validate(row) for row in rows]


@router.get("/documents/{slug}/files/{file_id}")
def download_document_file(
    slug: str,
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> FileResponse:
    _row_for_slug(db, user, slug, file_id)
    row = junior_shared_files.get_file(db, user, file_id)
    return FileResponse(row.storage_path, media_type=row.content_type, filename=row.filename)


@router.delete(
    "/documents/{slug}/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def delete_document_file(
    slug: str,
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> Response:
    """Return Response. A postponed `-> None` annotation makes FastAPI reject status 204."""
    _row_for_slug(db, user, slug, file_id)
    junior_shared_files.delete_file(db, user, file_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
