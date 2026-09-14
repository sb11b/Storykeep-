from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Article, Feed, GrokMessageFile, NoteMedia, OverlayAddition, User
from app.services.vault_paths import windows_safe_component

MAX_MEDIA_BYTES = 10 * 1024 * 1024
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
FILE_SUFFIXES = {".pdf", ".txt", ".md", ".docx", ".csv"}
ALLOWED_SUFFIXES = IMAGE_SUFFIXES | FILE_SUFFIXES
CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".csv": "text/csv",
}
MEDIA_RE = re.compile(r"/api/v1/media/([0-9a-fA-F-]{36})")


def _normalize_suffix(filename: str) -> str:
    suffix = Path(filename.replace("\\", "/")).suffix.lower()
    if suffix == ".jpeg":
        return ".jpg"
    return suffix


def _sniff_suffix(payload: bytes, suffix: str) -> str:
    if payload[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if payload[:2] == b"\xff\xd8":
        return ".jpg"
    if payload[:6] in {b"GIF87a", b"GIF89a"}:
        return ".gif"
    if payload[:4] == b"RIFF" and len(payload) >= 12 and payload[8:12] == b"WEBP":
        return ".webp"
    if payload[:4] == b"%PDF":
        return ".pdf"
    if payload[:8].startswith(b"\xd0\xcf\x11\xe0"):
        return ".doc"
    if suffix == ".docx" and payload[:2] == b"PK":
        return ".docx"
    return suffix


def storykeep_download_filename(media_id: UUID, content_type: str | None, filename: str | None = None) -> str:
    """Stable Save-as name: storykeep-{id}.jpg (or the real type's extension)."""
    suffix = _normalize_suffix(filename or "")
    if suffix not in ALLOWED_SUFFIXES:
        ctype = (content_type or "").split(";", 1)[0].strip().lower()
        suffix = {
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/png": ".png",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "application/pdf": ".pdf",
            "text/plain": ".txt",
            "text/markdown": ".md",
            "text/csv": ".csv",
        }.get(ctype, "")
        if not suffix and ctype.startswith("image/"):
            suffix = ".jpg"
        if not suffix:
            suffix = ".bin"
    if suffix == ".jpeg":
        suffix = ".jpg"
    return f"storykeep-{media_id}{suffix}"


def sniff_image_media_type(path: Path, declared: str | None) -> str:
    declared_type = (declared or "").split(";", 1)[0].strip().lower()
    if declared_type.startswith("image/"):
        if declared_type in {"image/jpg", "image/jpeg"}:
            return "image/jpeg"
        return declared_type
    try:
        head = path.read_bytes()[:16]
    except OSError:
        return declared_type or "application/octet-stream"
    if head[:2] == b"\xff\xd8":
        return "image/jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if head[:6] in {b"GIF87a", b"GIF89a"}:
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return declared_type or "application/octet-stream"


def note_media_root() -> Path:
    """Imagine/attach bytes go on DATA_DIR (prod volume /app/var). Pre-volume ids 404 if the file is gone — do not migrate ghosts."""
    root = settings.data_dir / "note-media"
    root.mkdir(parents=True, exist_ok=True)
    return root


def media_storage_path(user_id: UUID, media_id: UUID, suffix: str) -> Path:
    folder = note_media_root() / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{media_id}{suffix}"


def is_image_media(row: NoteMedia) -> bool:
    suffix = Path(row.filename).suffix.lower()
    if suffix == ".jpeg":
        suffix = ".jpg"
    return suffix in IMAGE_SUFFIXES or (row.content_type or "").startswith("image/")


def save_note_media(db: Session, user: User, filename: str, payload: bytes, content_type: str | None) -> NoteMedia:
    if not payload:
        raise ValueError("That file is empty.")
    if len(payload) > MAX_MEDIA_BYTES:
        raise ValueError("Attachments must be 10 MB or smaller.")
    suffix = _normalize_suffix(filename)
    if suffix == ".doc":
        raise ValueError("Legacy Word .doc is not supported. Save as .docx and attach again.")
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("Use PDF, TXT, MD, DOCX, CSV, PNG, JPG, GIF, or WebP.")
    suffix = _sniff_suffix(payload, suffix)
    if suffix == ".doc":
        raise ValueError("Legacy Word .doc is not supported. Save as .docx and attach again.")
    if suffix == ".docx":
        from app.services.docx_chat import inspect_docx_bytes

        inspect_docx_bytes(payload, filename)
    if suffix not in ALLOWED_SUFFIXES:
        raise ValueError("That file type is not allowed.")
    media_id = uuid4()
    path = media_storage_path(user.id, media_id, suffix)
    path.write_bytes(payload)
    safe_name = windows_safe_component(Path(filename).stem) + suffix
    row = NoteMedia(
        id=media_id,
        user_id=user.id,
        filename=safe_name,
        content_type=CONTENT_TYPES.get(suffix, content_type or "application/octet-stream"),
        storage_path=str(path),
        byte_size=len(payload),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def save_note_image(db: Session, user: User, filename: str, payload: bytes, content_type: str | None) -> NoteMedia:
    row = save_note_media(db, user, filename, payload, content_type)
    if not is_image_media(row):
        db.delete(row)
        db.commit()
        path = Path(row.storage_path)
        if path.is_file():
            path.unlink(missing_ok=True)
        raise ValueError("Use PNG, JPG, GIF, or WebP for images.")
    return row


def owned_media(db: Session, user: User, media_id: UUID) -> NoteMedia:
    row = db.get(NoteMedia, media_id)
    if not row or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="File not found")
    return row


def media_token(media_id: UUID) -> str:
    return f"/api/v1/media/{media_id}"


def media_is_referenced(db: Session, user: User, media_id: UUID) -> bool:
    token = media_token(media_id)
    for row in db.scalars(select(OverlayAddition).where(OverlayAddition.user_id == user.id)):
        if token in (row.markdown or ""):
            return True
    articles = db.scalars(
        select(Article)
        .join(Feed, Article.feed_id == Feed.id)
        .where(Feed.user_id == user.id)
    ).all()
    for row in articles:
        hay = f"{row.content_text or ''}\n{row.content_html or ''}"
        if token in hay:
            return True
    if db.scalar(select(GrokMessageFile.id).where(GrokMessageFile.media_id == media_id).limit(1)):
        return True
    return False


def delete_note_media(db: Session, user: User, media_id: UUID) -> dict[str, object]:
    row = owned_media(db, user, media_id)
    if media_is_referenced(db, user, media_id):
        return {"ok": True, "deleted": False}
    path = Path(row.storage_path)
    db.delete(row)
    db.commit()
    if path.is_file():
        path.unlink(missing_ok=True)
    return {"ok": True, "deleted": True}


def markdown_image(row: NoteMedia) -> str:
    alt = Path(row.filename).stem.replace("-", " ")
    return f"![{alt}](/api/v1/media/{row.id})"


def markdown_attachment(row: NoteMedia) -> str:
    label = row.filename or "attachment"
    return f"[{label}](/api/v1/media/{row.id})"


def markdown_for_media(row: NoteMedia) -> str:
    if is_image_media(row):
        return markdown_image(row)
    return markdown_attachment(row)


def media_ids_in_markdown(markdown: str) -> list[UUID]:
    found: list[UUID] = []
    for match in MEDIA_RE.finditer(markdown or ""):
        try:
            found.append(UUID(match.group(1)))
        except ValueError:
            continue
    return found
