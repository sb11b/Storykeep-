from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone
from uuid import UUID

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Article, Correction, NoteMedia, OverlayAddition, OverlayHighlight, User
from app.services.note_media import media_ids_in_markdown
from app.services.vault_paths import overlay_relpath

YAML_ESCAPE = str.maketrans({'"': '\\"', "\\": "\\\\"})


def build_obsidian_pack(db: Session, user: User) -> bytes:
    highlights = db.scalars(
        select(OverlayHighlight)
        .where(OverlayHighlight.user_id == user.id)
        .options(selectinload(OverlayHighlight.article).selectinload(Article.feed))
        .order_by(OverlayHighlight.created_at.asc())
    ).all()
    additions = db.scalars(
        select(OverlayAddition)
        .where(OverlayAddition.user_id == user.id)
        .options(selectinload(OverlayAddition.article))
        .order_by(OverlayAddition.created_at.asc())
    ).all()
    corrections = db.scalars(
        select(Correction)
        .where(Correction.user_id == user.id)
        .options(selectinload(Correction.article))
        .order_by(Correction.created_at.asc())
    ).all()

    grouped_highlights: dict[UUID, list[OverlayHighlight]] = {}
    for row in highlights:
        grouped_highlights.setdefault(row.article_id, []).append(row)
    latest_correction: dict[UUID, Correction] = {}
    for row in corrections:
        latest_correction[row.article_id] = row

    index_lines = [
        "---",
        'kind: index',
        "updated: " + _iso(datetime.now(timezone.utc)),
        "---",
        "",
        "# StoryKeep overlay",
        "",
        "This pack is additive. Unzip into the vault root. It does not modify original notes.",
        "Original vault paths are not listed here. Merge Corrections by hand if you want those edits in the source file.",
        "",
        "## Files in this pack",
        "",
    ]
    listed = 0
    packed_media: set[UUID] = set()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for article_id, rows in grouped_highlights.items():
            article = rows[0].article
            source_ref = _source_ref(article)
            path = overlay_relpath("highlight", source_ref, str(article_id))
            body = [
                _frontmatter(rows[0].id, "highlight", source_ref, rows[-1].created_at),
                "",
                f"# Highlights · {article.title}",
                "",
            ]
            for row in rows:
                body.append(f"> {row.quote.strip()}")
                body.append("")
                if row.note and row.note.strip() != row.quote.strip():
                    body.append(row.note.strip())
                    body.append("")
            zf.writestr(path, "\n".join(body))
            index_lines.append(f"- `{path}` · highlight · `{article.id}` · {_iso(rows[-1].created_at)}")
            listed += 1

        for row in additions:
            pack_kind = "correction" if getattr(row, "is_correction", False) else "addition"
            path = overlay_relpath(pack_kind, None, f"{row.title}-{str(row.id)[:8]}")
            source_ref = _source_ref(row.article) if row.article else None
            packed_body = _pack_addition_markdown(zf, db, user, row.markdown, packed_media)
            text = [
                _frontmatter(row.id, pack_kind, source_ref, row.updated_at or row.created_at),
                "",
                f"# {row.title}",
                "",
                packed_body,
                "",
            ]
            zf.writestr(path, "\n".join(text))
            index_lines.append(f"- `{path}` · {pack_kind} · `{row.id}` · {_iso(row.created_at)}")
            listed += 1

        for article_id, row in latest_correction.items():
            article = row.article
            source_ref = _source_ref(article)
            path = overlay_relpath("correction", source_ref, str(article_id))
            text = [
                _frontmatter(row.id, "correction", source_ref, row.created_at),
                "",
                f"# Correction · {article.title}",
                "",
                "StoryKeep-owned copy. The original imported note was not overwritten.",
                "",
                row.markdown,
                "",
            ]
            zf.writestr(path, "\n".join(text))
            index_lines.append(f"- `{path}` · correction · `{article.id}` · {_iso(row.created_at)}")
            listed += 1

        if listed == 0:
            index_lines.append("- (empty pack — add a highlight, addition, or correction in StoryKeep)")
        zf.writestr("StoryKeep/Index.md", "\n".join(index_lines) + "\n")

    return buf.getvalue()


def _pack_addition_markdown(
    zf: zipfile.ZipFile, db: Session, user: User, markdown: str, packed_media: set[UUID]
) -> str:
    rewritten = markdown or ""
    for media_id in media_ids_in_markdown(rewritten):
        row = db.get(NoteMedia, media_id)
        if not row or row.user_id != user.id:
            continue
        src = Path(row.storage_path)
        suffix = src.suffix or Path(row.filename).suffix or ".bin"
        name = f"{media_id}{suffix}"
        zip_path = f"StoryKeep/Additions/media/{name}"
        if media_id not in packed_media and src.is_file():
            zf.write(src, zip_path)
            packed_media.add(media_id)
        rewritten = rewritten.replace(f"/api/v1/media/{media_id}", f"media/{name}")
        rewritten = rewritten.replace(f"/api/v1/media/{str(media_id).upper()}", f"media/{name}")
    return rewritten


def _source_ref(article: Article | None) -> str | None:
    if not article:
        return None
    return article.source_ref or article.obsidian_path


def _iso(value: datetime | None) -> str:
    if not value:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _frontmatter(entity_id, kind: str, source_ref: str | None, updated: datetime | None) -> str:
    ref = (source_ref or "").translate(YAML_ESCAPE)
    return "\n".join(
        [
            "---",
            f"storykeep_id: {entity_id}",
            f"kind: {kind}",
            f'source_ref: "{ref}"',
            f"updated: {_iso(updated)}",
            "---",
        ]
    )
