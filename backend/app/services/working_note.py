from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import Article, User
from app.services.destination import is_composed_guid
from app.services.include_chunk import WORKING_NOTE_CHAR_CAP, parse_sections, resolve_include_slice
from app.services.note_revisions import stored_note_markdown
from app.services.vault_import import update_composed_note

_SECTION_N = re.compile(r"section\s+(\d+)", re.I)
_FENCE = re.compile(r"```(?:markdown|md)?\s*\n(.*?)```", re.S | re.I)
_SUBHEAD = re.compile(r"(?m)^(#{2,6})\s+(.+?)\s*$")


def heading_from_instruction(message: str, body: str) -> str | None:
    text = (message or "").lower()
    if not text.strip() or not body:
        return None
    sections = parse_sections(body)
    for label, _start, _end in sections:
        lowered = label.strip().lower()
        if lowered and lowered != "opening" and lowered in text:
            return label
    numbered = _SECTION_N.search(text)
    if not numbered:
        return None
    index = int(numbered.group(1))
    headings = [match.group(2).strip() for match in _SUBHEAD.finditer(body or "") if match.group(2).strip()]
    if 1 <= index <= len(headings):
        return headings[index - 1]
    return None


def extract_apply_markdown(reply: str) -> str:
    text = (reply or "").strip()
    if not text:
        raise ValueError("That reply is empty.")
    match = _FENCE.search(text)
    if match:
        fenced = (match.group(1) or "").strip()
        if fenced:
            return fenced
    return text


def _replace_span(source: str, start: int, end: int, replacement: str) -> str:
    chunk = (replacement or "").strip("\n")
    prefix = source[: max(0, start)]
    suffix = source[max(end, start) :]
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    if suffix and not suffix.startswith("\n") and chunk:
        chunk += "\n"
    return f"{prefix}{chunk}{suffix}"


def merge_working_note(
    source: str,
    reply: str,
    *,
    mode: str | None = None,
    heading: str | None = None,
    offset: int = 0,
) -> str:
    incoming = extract_apply_markdown(reply)
    body = source or ""
    cleaned_mode = (mode or "auto").strip().lower()
    if cleaned_mode == "heading" and (heading or "").strip():
        want = heading.strip().lower()
        sections = parse_sections(body)
        match = next((item for item in sections if item[0].strip().lower() == want), None)
        if match is None:
            match = next((item for item in sections if want in item[0].strip().lower()), None)
        if match is None:
            raise ValueError(f"No heading named {heading!r} in this note.")
        _label, start, end = match
        return _replace_span(body, start, end, incoming)
    slice = resolve_include_slice(
        body,
        mode=cleaned_mode,
        heading=heading,
        offset=offset or 0,
        cap=WORKING_NOTE_CHAR_CAP,
        hard_max=WORKING_NOTE_CHAR_CAP,
    )
    if slice.has_more or slice.offset:
        end = slice.next_offset if slice.next_offset is not None else slice.offset + slice.chars
        return _replace_span(body, slice.offset, end, incoming)
    return incoming


def apply_junior_reply(
    db: Session,
    user: User,
    article: Article,
    reply: str,
    *,
    mode: str | None = None,
    heading: str | None = None,
    offset: int = 0,
    confirm_short: bool = False,
) -> Article:
    if not is_composed_guid(article.guid):
        raise ValueError("Imported vault notes stay read-only. Work in Junior is for StoryKeep-authored notes.")
    current = stored_note_markdown(article, db, user)
    next_body = merge_working_note(current, reply, mode=mode, heading=heading, offset=offset)
    return update_composed_note(
        db,
        user,
        article,
        article.title,
        next_body,
        confirm_short=confirm_short,
        snapshot=True,
    )
