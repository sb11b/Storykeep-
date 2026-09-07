from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Correction, OverlayAddition, User
from app.presenters import article_out
from app.routers.articles import _owned_article
from app.schemas import CorrectionIn, CorrectionOut, OverlayAdditionIn, OverlayAdditionOut, VaultImportOut
from app.services import changelog
from app.services.overlay_pack import build_obsidian_pack
from app.services.vault_import import import_obsidian_zip

router = APIRouter(tags=["overlay"])


@router.post("/sources/obsidian/import", response_model=VaultImportOut)
async def import_obsidian_vault(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VaultImportOut:
    payload = await file.read()
    if len(payload) > 80 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Zip is larger than 80 MB.")
    try:
        result = import_obsidian_zip(db, user, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return VaultImportOut(**result)


@router.get("/export/obsidian-pack")
def download_obsidian_pack(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    blob = build_obsidian_pack(db, user)
    return Response(
        content=blob,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="storykeep-obsidian-pack.zip"'},
    )


@router.post("/storykeep-notes", response_model=OverlayAdditionOut, status_code=201)
def create_standalone_addition(
    payload: OverlayAdditionIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OverlayAdditionOut:
    row = OverlayAddition(
        user_id=user.id,
        article_id=None,
        title=payload.title.strip(),
        markdown=payload.markdown,
    )
    db.add(row)
    db.flush()
    changelog.record(db, user.id, "addition", row.id, "upsert", {"standalone": True})
    db.commit()
    db.refresh(row)
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
