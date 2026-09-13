from __future__ import annotations

import re
from typing import Any

from app.models import User

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,15}$")
MAX_SHELVES = 24


def slugify_shelf_name(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")[:16]
    return base or "shelf"


def list_custom_note_shelves(user: User) -> list[dict[str, str]]:
    raw = (user.preferences or {}).get("custom_note_shelves") or []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        shelf_id = str(row.get("id") or "").strip().lower()
        label = str(row.get("name") or "").strip()
        if SLUG_RE.match(shelf_id) and label:
            out.append({"id": shelf_id, "name": label[:80]})
    return out


def is_custom_note_shelf(user: User | None, shelf: str) -> bool:
    if not user:
        return False
    raw = (shelf or "").strip().lower()
    return any(row["id"] == raw for row in list_custom_note_shelves(user))


def normalize_custom_shelves_payload(items: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError("custom_note_shelves must be a list.")
    if len(items) > MAX_SHELVES:
        raise ValueError(f"You can keep at most {MAX_SHELVES} custom shelves.")
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    out: list[dict[str, str]] = []
    for row in items:
        if not isinstance(row, dict):
            raise ValueError("Each custom shelf must be an object.")
        name = str(row.get("name") or "").strip()
        if not name:
            raise ValueError("Custom shelf name is required.")
        if len(name) > 80:
            raise ValueError("Custom shelf name must be 80 characters or fewer.")
        name_key = name.casefold()
        if name_key in seen_names:
            raise ValueError(f'You already have a shelf named "{name}".')
        seen_names.add(name_key)
        shelf_id = str(row.get("id") or slugify_shelf_name(name)).strip().lower()
        if not SLUG_RE.match(shelf_id):
            raise ValueError("Custom shelf id must be 1–16 lowercase letters, numbers, hyphens, or underscores.")
        if shelf_id in seen_ids:
            raise ValueError(f'Shelf id "{shelf_id}" is duplicated.')
        seen_ids.add(shelf_id)
        out.append({"id": shelf_id, "name": name})
    return out
