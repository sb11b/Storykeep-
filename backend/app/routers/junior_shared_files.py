from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.schemas import JuniorDocumentFileOut
from app.services import junior_shared_files

router = APIRouter(tags=["junior-shared-files"])

# CRITICAL (verified in review): the file has `from __future__ import annotations`, which turns
# the `-> None` return annotation into the STRING "None". FastAPI evaluates that to NoneType —
# a type — and asserts "Status code 204 must not have a response body". The delete route
# therefore MUST carry BOTH response_class=Response AND response_model=None (below). Do not
# simplify this to plain status_code=204 — it crashes at import.

_UPLOAD_CHUNK_BYTES = 1024 * 1024  # 1 MB streaming granularity
# Multipart overhead (boundaries, part headers) on top of the raw file bytes.
_UPLOAD_OVERHEAD_BYTES = 8192


@router.post("/documents/{slug}/files", response_model=JuniorDocumentFileOut, status_code=201)
async def upload_document_file(
    slug: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> JuniorDocumentFileOut:
    # SEC-1 fix (verified in review): never materialize an unbounded body.
    # Reject on the ANNOUNCED content-length first (cheap, covers honest
    # clients), then stream in 1MB chunks with a hard ceiling (catches a lying
    # or chunked length — the definitive guard). A plain `await file.read()`
    # materializes the WHOLE upload before the cap fires and lets an
    # authenticated caller OOM the worker with a multi-GB body.
    announced = request.headers.get("content-length")
    if announced:
        try:
            if int(announced) > junior_shared_files.MAX_FILE_BYTES + _UPLOAD_OVERHEAD_BYTES:
                raise HTTPException(status_code=400, detail="That file is larger than 40 MB.")
        except ValueError:
            pass  # malformed header — fall through to the streaming ceiling
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > junior_shared_files.MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail="That file is larger than 40 MB.")
        chunks.append(chunk)
    payload = b"".join(chunks)
    row = junior_shared_files.save_file(db, user, slug, file.filename or "file", payload, file.content_type)
    return JuniorDocumentFileOut.model_validate(row)


@router.get("/documents/{slug}/files", response_model=list[JuniorDocumentFileOut])
def list_document_files(
    slug: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> list[JuniorDocumentFileOut]:
    return [JuniorDocumentFileOut.model_validate(r) for r in junior_shared_files.list_files(db, user, slug)]


@router.get("/files/{file_id}")
def download_document_file(
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> FileResponse:
    row = junior_shared_files.get_file(db, user, file_id)
    return FileResponse(
        row.storage_path,
        media_type=row.content_type,
        filename=row.filename,
        content_disposition_type="attachment",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"},
    )


@router.delete("/files/{file_id}", status_code=204, response_class=Response, response_model=None)
def delete_document_file(
    file_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
) -> None:
    junior_shared_files.delete_file(db, user, file_id)
