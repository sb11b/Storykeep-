from __future__ import annotations

import base64
import io
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import GrokMessage, GrokMessageFile, NoteMedia, User
from app.services.file_extract import extract_document
from app.services.note_media import is_image_media, owned_media

logger = logging.getLogger(__name__)

MAX_ATTACHMENTS = 5
ATTACHMENT_CHAR_CAP = 12_000
PDF_PAGE_CAP = 8
MAX_VISION_SIDE = 1280
MAX_VISION_RAW_BYTES = 400_000
MAX_VISION_ENCODED_BYTES = 1_200_000

EXTRACTABLE_SUFFIXES = {".pdf", ".txt", ".md", ".markdown", ".csv", ".docx"}


def model_supports_vision(model: str | None) -> bool:
    name = (model or "").strip().lower()
    if not name:
        return False
    if "vision" in name:
        return True
    return name.startswith("grok-4")


def file_payload(row: GrokMessageFile) -> dict[str, Any]:
    return {
        "media_id": row.media_id,
        "filename": row.filename,
        "content_type": row.content_type,
        "kind": row.kind,
        "extract_text": row.extract_text or "",
        "byte_size": row.byte_size,
        "url": f"/api/v1/media/{row.media_id}",
    }


def extract_text_for_media(row: NoteMedia) -> str:
    if is_image_media(row):
        return ""
    suffix = Path(row.filename).suffix.lower()
    if suffix not in EXTRACTABLE_SUFFIXES:
        return ""
    path = Path(row.storage_path)
    if not path.is_file():
        return ""
    try:
        _title, text = extract_document(row.filename, path.read_bytes(), max_pdf_pages=PDF_PAGE_CAP)
    except ValueError:
        return ""
    except Exception:
        logger.exception("Could not extract chat attachment %s", row.filename)
        return ""
    return (text or "").strip()[:ATTACHMENT_CHAR_CAP]


def resolve_owned_media(db: Session, user: User, media_ids: list[UUID]) -> list[NoteMedia]:
    if len(media_ids) > MAX_ATTACHMENTS:
        raise HTTPException(status_code=400, detail=f"Attach up to {MAX_ATTACHMENTS} files.")
    rows: list[NoteMedia] = []
    seen: set[UUID] = set()
    for media_id in media_ids:
        if media_id in seen:
            continue
        seen.add(media_id)
        rows.append(owned_media(db, user, media_id))
    return rows


def attach_to_message(
    db: Session,
    user: User,
    message: GrokMessage,
    media_ids: list[UUID],
    *,
    allow_assistant: bool = False,
) -> list[GrokMessageFile]:
    if message.role == "assistant" and allow_assistant:
        pass
    elif message.role != "user":
        raise HTTPException(status_code=400, detail="Files attach to your message, not the reply.")
    rows = resolve_owned_media(db, user, media_ids)
    attached: list[GrokMessageFile] = []
    for media in rows:
        kind = "image" if is_image_media(media) else "file"
        item = GrokMessageFile(
            message_id=message.id,
            media_id=media.id,
            filename=media.filename,
            content_type=media.content_type,
            kind=kind,
            byte_size=media.byte_size,
            extract_text=extract_text_for_media(media) or None,
        )
        db.add(item)
        attached.append(item)
    db.flush()
    return attached


def preview_files(db: Session, user: User, media_ids: list[UUID]) -> list[dict[str, Any]]:
    rows = resolve_owned_media(db, user, media_ids)
    out: list[dict[str, Any]] = []
    for media in rows:
        kind = "image" if is_image_media(media) else "file"
        out.append(
            {
                "media_id": media.id,
                "filename": media.filename,
                "content_type": media.content_type,
                "kind": kind,
                "extract_text": extract_text_for_media(media),
                "byte_size": media.byte_size,
                "url": f"/api/v1/media/{media.id}",
            }
        )
    return out


def merge_attachment_text(content: str, files: list[dict[str, Any]] | None, *, include_extracts: bool) -> str:
    text = (content or "").strip()
    if not files:
        return text
    blocks: list[str] = []
    remaining = ATTACHMENT_CHAR_CAP
    for item in files:
        name = (item.get("filename") or "attachment").strip() or "attachment"
        kind = item.get("kind") or "file"
        if kind == "image":
            blocks.append(f"Attached image: {name}")
            continue
        extract = (item.get("extract_text") or "").strip() if include_extracts else ""
        if include_extracts and extract:
            clipped = extract if len(extract) <= remaining else extract[: max(remaining - 1, 0)].rstrip() + "…"
            remaining = max(0, remaining - len(clipped))
            blocks.append(f"Attached file {name}:\n{clipped}")
            if remaining <= 0:
                break
        else:
            blocks.append(f"Attached file: {name}")
    joined = "\n\n".join(blocks)
    if text and joined:
        return f"{text}\n\n{joined}"
    return text or joined


def vision_data_url(payload: bytes, content_type: str) -> str | None:
    """Compress before sending pixels. Never ship a raw 10 MB blob to xAI."""
    mime = (content_type or "image/jpeg").split(";")[0].strip() or "image/jpeg"
    if len(payload) <= MAX_VISION_RAW_BYTES and mime.startswith("image/"):
        encoded = base64.b64encode(payload).decode("ascii")
        return f"data:{mime};base64,{encoded}"
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(payload))
        image = image.convert("RGB")
        image.thumbnail((MAX_VISION_SIDE, MAX_VISION_SIDE))
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=80, optimize=True)
        data = buf.getvalue()
    except Exception:
        logger.exception("Could not compress chat image for vision")
        return None
    if not data or len(data) > MAX_VISION_ENCODED_BYTES:
        return None
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def vision_parts(db: Session, user: User, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    for item in files:
        if item.get("kind") != "image":
            continue
        media_id = item.get("media_id")
        if not media_id:
            continue
        try:
            media = owned_media(db, user, media_id if isinstance(media_id, UUID) else UUID(str(media_id)))
        except HTTPException:
            continue
        path = Path(media.storage_path)
        if not path.is_file():
            continue
        url = vision_data_url(path.read_bytes(), media.content_type)
        if not url:
            continue
        parts.append({"type": "image_url", "image_url": {"url": url, "detail": "auto"}})
    return parts
