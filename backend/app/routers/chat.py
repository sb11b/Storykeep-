from __future__ import annotations

from app.schemas import GrokMessageFileOut, GrokMessageOut
from app.services import message_crypto


def _file_out(row) -> GrokMessageFileOut:
    return GrokMessageFileOut(
        media_id=row.media_id,
        filename=row.filename,
        content_type=row.content_type,
        kind=row.kind,
        url=f"/api/v1/media/{row.media_id}",
        byte_size=row.byte_size,
        extract_text=getattr(row, "extract_text", None) or None,
    )


def _message_out(row, *, crypto_enabled: bool = False) -> GrokMessageOut:
    body = message_crypto.message_body_out(row, crypto_enabled=crypto_enabled)
    return GrokMessageOut(
        id=row.id,
        role=row.role,
        content=body.get("content"),
        iv=body.get("iv"),
        ct=body.get("ct"),
        encrypted=bool(body.get("encrypted")),
        created_at=row.created_at,
        files=[_file_out(item) for item in (row.files or [])],
    )
