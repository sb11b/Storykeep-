from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Correction, OverlayAddition, User
from app.presenters import article_out
from app.routers.articles import _owned_article
from app.schemas import ArticleOut, CorrectionIn, CorrectionOut, OverlayAdditionIn, OverlayAdditionOut, VaultImportOut
from app.services import changelog
from app.services.overlay_pack import build_obsidian_pack
from app.services.file_ingest import MAX_UPLOAD_BYTES, ingest_upload, original_file_path
from app.services.vault_import import MAX_VAULT_ZIP_BYTES, create_composed_note, import_obsidian_zip

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
        article = create_composed_note(db, user, payload.title, payload.markdown, payload.tags)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    loaded = _owned_article(db, user, article.id)
    return article_out(loaded)


@router.post("/storykeep-notes", response_model=OverlayAdditionOut, status_code=201)
def create_standalone_addition(
    payload: OverlayAdditionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OverlayAdditionOut:
    try:
        article = create_composed_note(db, user, payload.title, payload.markdown, payload.tags)
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
    row = OverlayAddition(
        user_id=user.id,
        article_id=article.id,
        title=payload.title.strip(),
        markdown=payload.markdown,
    )
    db.add(row)
    db.flush()
    changelog.record(db, user.id, "addition", row.id, "upsert", {"article_id": str(article.id)})
    db.commit()
    db.refresh(row)
    return OverlayAdditionOut.model_validate(row)


@router.post("/articles/{article_id}/corrections", response_model=CorrectionOut, status_code=201)
def create_correction(
    article_id: UUID,
    payload: CorrectionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CorrectionOut:
    article = _owned_article(db, user, article_id)
    row = Correction(user_id=user.id, article_id=article.id, markdown=payload.markdown)
    db.add(row)
    db.flush()
    changelog.record(db, user.id, "correction", row.id, "upsert", {"article_id": str(article.id)})
    db.commit()
    db.refresh(row)
    return CorrectionOut.model_validate(row)


@router.get("/articles/{article_id}/overlay", response_model=dict)
def article_overlay(article_id: UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    article = _owned_article(db, user, article_id)
    packed = article_out(article)
    return {
        "highlights": [item.model_dump() for item in packed.overlay_highlights],
        "additions": [item.model_dump() for item in packed.overlay_additions],
        "corrections": [item.model_dump() for item in packed.corrections],
    }
