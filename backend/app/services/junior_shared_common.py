"""Low-level helpers shared by the Junior shared-memory modules.

Deliberately dependency-free (stdlib + fastapi only) so that
``junior_shared_memory`` and ``junior_shared_documents`` can both import it
without creating a cycle: previously documents imported these from memory,
and memory re-exported documents, so importing documents first raised
ImportError.
"""

from __future__ import annotations

import re
from uuid import UUID

from fastapi import HTTPException

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

PAGE_MAX = 100
PAGE_DEFAULT = 50


def clamp_page_limit(limit: int | None, *, default: int = PAGE_DEFAULT) -> int:
    if limit is None:
        return default
    return max(1, min(int(limit), PAGE_MAX))


def _as_uuid(value: UUID | str | None) -> UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def normalize_slug(value: str | None) -> str:
    slug = (value or "").strip().lower()
    if not SLUG_RE.match(slug) or len(slug) > 64:
        raise HTTPException(status_code=400, detail="Invalid project slug")
    return slug
