from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import OverlayAddition, User
from app.presenters import article_out
from app.routers.articles import _article_payload, _owned_article
from app.schemas import (
    ArticleOut,
    CorrectionIn,
    CorrectionOut,
    DestinationIn,
    OverlayAdditionIn,
    OverlayAdditionOut,
    VaultImportOut,
)
from app.services import changelog
from app.services.corrections import unlink_correction, upsert_correction
from app.services.note_media import (
    delete_note_media,
    is_image_media,
    markdown_for_media,
    owned_media,
    save_note_image,
    save_note_media,
)
from app.services.overlay_pack import build_obsidian_pack
from app.services.file_ingest import MAX_UPLOAD_BYTES, ingest_upload, original_file_path
from app.services.vault_import import (
    MAX_VAULT_ZIP_BYTES,
    create_composed_note,
    import_obsidian_zip,
    set_composed_destination,
    update_composed_note,
)

router = APIRouter(tags=["overlay"])


@router.post("/sources/obsidian/import", response_model=VaultImportOut)
async def import_obsidian_vault(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VaultImportOut:
    payload = await file.read()
    if len(payload) > MAX_VAULT_ZIP_BYTES:
        raise HTTPException(status_code=400, detail="Zip is larger than 100 MB.")
    try:
        result = import_obsidian_zip(db, user, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return VaultImportOut(**result)


@router.post("/sources/upload", response_model=ArticleOut, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    tags: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ArticleOut:
    payload = await file.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="That file is larger than 40 MB.")
    labels = [part.strip() for part in (tags or "").replace("#", ",").split(",") if part.strip()]
    try:
        article = ingest_upload(db, user, file.filename or "upload", payload, title, labels)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return article_out(_owned_article(db, user, article.id))


@router.get("/articles/{article_id}/file")
def download_original_file(
    article_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    article = _owned_article(db, user, article_id)
    path = original_file_path(article)
    if path is None:
        raise HTTPException(status_code=404, detail="Original file is not stored for this article.")
    return FileResponse(path, filename=article.source_ref or path.name)


@router.get("/export/obsidian-pack")
def download_obsidian_pack(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    blob = build_obsidian_pack(db, user)
    return Response(
        content=blob,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="storykeep-obsidian-pack.zip"'},
    )


@router.post("/sources/obsidian/notes", response_model=ArticleOut, status_code=201)
def compose_vault_note(
    payload: OverlayAdditionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ArticleOut:
    try:
        article = create_composed_note(
            db,
            user,
            payload.title,
            payload.markdown,
            payload.tags,
            destination=payload.destination,
            folder_id=payload.folder_id,
            parent_id=payload.parent_id,
            is_correction=payload.is_correction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _article_payload(db, user, article.id)


@router.patch("/articles/{article_id}/storykeep-note", response_model=ArticleOut)
def edit_composed_note(
    article_id: UUID,
    payload: OverlayAdditionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ArticleOut:
    article = _owned_article(db, user, article_id)
    try:
        update_composed_note(
            db,
            user,
            article,
            payload.title,
            payload.markdown,
            payload.is_correction,
            folder_id=payload.folder_id,
            commit=False,
        )
        dest = payload.destination or getattr(article, "destination", None) or "additions"
        set_composed_destination(
            db, user, article, dest, payload.is_correction, folder_id=payload.folder_id, commit=False
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _article_payload(db, user, article.id)


@router.patch("/articles/{article_id}/destination", response_model=ArticleOut)
def move_article_filing(
    article_id: UUID,
    payload: DestinationIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ArticleOut:
    article = _owned_article(db, user, article_id)
    try:
        from app.services.filing import set_article_filing

        set_article_filing(
            db,
            user,
            article,
            payload.destination,
            folder_id=payload.folder_id,
            is_correction=payload.is_correction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _article_payload(db, user, article.id)


@router.post("/media", status_code=201)
async def upload_note_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    payload = await file.read()
    try:
        row = save_note_media(db, user, file.filename or "attachment.bin", payload, file.content_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    kind = "image" if is_image_media(row) else "file"
    return {
        "id": str(row.id),
        "url": f"/api/v1/media/{row.id}",
        "markdown": markdown_for_media(row),
        "filename": row.filename,
        "kind": kind,
    }


@router.get("/media/{media_id}")
def get_note_media(
    media_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    row = owned_media(db, user, media_id)
    path = Path(row.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File is missing.")
    return FileResponse(path, media_type=row.content_type, filename=row.filename)


@router.delete("/media/{media_id}")
def remove_note_media(
    media_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    return delete_note_media(db, user, media_id)


@router.post("/storykeep-notes", response_model=OverlayAdditionOut, status_code=201)
def create_standalone_addition(
    payload: OverlayAdditionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OverlayAdditionOut:
    try:
        article = create_composed_note(
            db,
            user,
            payload.title,
            payload.markdown,
            payload.tags,
            destination=payload.destination,
            folder_id=payload.folder_id,
            parent_id=payload.parent_id,
            is_correction=payload.is_correction,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    loaded = _owned_article(db, user, article.id)
    row = loaded.overlay_additions[-1] if loaded.overlay_additions else None
    if row is None:
        raise HTTPException(status_code=500, detail="Note was saved without an overlay copy.")
    return OverlayAdditionOut.model_validate(row)


@router.post("/articles/{article_id}/additions", response_model=OverlayAdditionOut, status_code=201)
def create_addition(
    article_id: UUID,
    payload: OverlayAdditionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OverlayAdditionOut:
    article = _owned_article(db, user, article_id)
    if payload.is_correction:
        raise HTTPException(
            status_code=400,
            detail="Corrections attach to this article directly. Use the correction save path instead of a filed note.",
        )
    try:
        child = create_composed_note(
            db,
            user,
            payload.title.strip(),
            payload.markdown,
            payload.tags,
            destination=payload.destination or "notes",
            folder_id=payload.folder_id,
            parent_id=article.id,
            is_correction=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    loaded = _owned_article(db, user, child.id)
    row = loaded.overlay_additions[-1] if loaded.overlay_additions else None
    if row is None:
        raise HTTPException(status_code=500, detail="Note was saved without an overlay copy.")
    return OverlayAdditionOut.model_validate(row)


@router.post("/articles/{article_id}/corrections", response_model=CorrectionOut)
def save_correction(
    article_id: UUID,
    payload: CorrectionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CorrectionOut:
    article = _owned_article(db, user, article_id)
    try:
        row = upsert_correction(db, user, article, payload.markdown)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CorrectionOut.model_validate(row)


@router.delete("/articles/{article_id}/corrections")
def remove_correction_link(
    article_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, bool]:
    _owned_article(db, user, article_id)
    unlink_correction(db, user, article_id)
    return {"ok": True}


@router.get("/articles/{article_id}/overlay", response_model=dict)
def article_overlay(article_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    article = _owned_article(db, user, article_id)
    packed = article_out(article)
    return {
        "highlights": [item.model_dump() for item in packed.overlay_highlights],
        "additions": [item.model_dump() for item in packed.overlay_additions],
        "corrections": [item.model_dump() for item in packed.corrections],
    }
