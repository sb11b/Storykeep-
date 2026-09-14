from __future__ import annotations

import re
from dataclasses import dataclass

# Per-turn include slice. Never the whole vault.
INCLUDE_TURN_CHAR_CAP = 10_000
INCLUDE_TURN_CHAR_MAX = 12_000

INCLUDE_MODES = ("auto", "selection", "heading", "chunk")

_MD_HEADING = re.compile(r"(?m)^(#{1,6})\s+(.+?)\s*$")
_HTML_HEADING = re.compile(r"(?is)<h([1-6])\b[^>]*>(.*?)</h\1>")
_TAG = re.compile(r"(?s)<[^>]+>")


@dataclass(frozen=True)
class IncludeSlice:
    text: str
    label: str
    chars: int
    mode: str
    offset: int
    next_offset: int | None
    next_heading: str | None
    has_more: bool

    @property
    def chip(self) -> str:
        return format_include_chip(self.label, self.chars)


def format_include_chip(label: str, chars: int) -> str:
    title = (label or "Slice").strip() or "Slice"
    return f"§ {title} ({chars:,} chars)"


def _strip_html(raw: str) -> str:
    text = _HTML_HEADING.sub(
        lambda match: "\n" + ("#" * int(match.group(1))) + " " + _TAG.sub("", match.group(2)).strip() + "\n",
        raw or "",
    )
    text = _TAG.sub(" ", text)
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", text)).strip()


def normalize_include_body(raw: str | None, html: str | None = None) -> str:
    text = (raw or "").strip()
    if _MD_HEADING.search(text):
        return text
    if html and _HTML_HEADING.search(html):
        return _strip_html(html)
    if _HTML_HEADING.search(text):
        return _strip_html(text)
    return text


def parse_sections(body: str) -> list[tuple[str, int, int]]:
    """Return (title, start, end) ranges in `body`, including a lead-in Opening if needed."""
    text = body or ""
    matches = list(_MD_HEADING.finditer(text))
    if not matches:
        return [("Opening", 0, len(text))] if text else []
    sections: list[tuple[str, int, int]] = []
    if matches[0].start() > 0 and text[: matches[0].start()].strip():
        sections.append(("Opening", 0, matches[0].start()))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        title = match.group(2).strip() or "Section"
        sections.append((title, match.start(), end))
    return sections


def clamp_slice(text: str, cap: int = INCLUDE_TURN_CHAR_CAP) -> str:
    cleaned = text or ""
    limit = min(max(1, cap), INCLUDE_TURN_CHAR_MAX)
    if len(cleaned) <= limit:
        return cleaned
    cut = cleaned[:limit]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip()


def _needs_chunk(body: str) -> bool:
    return len(body or "") > INCLUDE_TURN_CHAR_CAP


def resolve_include_slice(
    body: str,
    *,
    mode: str | None = None,
    selection: str | None = None,
    heading: str | None = None,
    offset: int = 0,
    title: str | None = None,
    html: str | None = None,
) -> IncludeSlice:
    source = normalize_include_body(body, html)
    cleaned_mode = (mode or "auto").strip().lower()
    if cleaned_mode not in INCLUDE_MODES:
        cleaned_mode = "auto"
    fallback_label = (title or "").strip() or "Included"

    if cleaned_mode == "selection":
        quote = re.sub(r"\s+", " ", (selection or "").strip())
        if not quote:
            raise ValueError("Highlight text in the reader, then Include selection.")
        text = clamp_slice(quote)
        found = source.find(quote[: min(len(quote), 80)]) if source else -1
        start = found if found >= 0 else 0
        end = start + len(text)
        has_more = end < len(source)
        next_heading = None
        if has_more:
            for label, sec_start, _sec_end in parse_sections(source):
                if sec_start >= end:
                    next_heading = label
                    break
        return IncludeSlice(
            text=text,
            label="Selection",
            chars=len(text),
            mode="selection",
            offset=start,
            next_offset=end if has_more else None,
            next_heading=next_heading,
            has_more=has_more,
        )

    sections = parse_sections(source)

    if cleaned_mode == "heading":
        want = (heading or "").strip().lower()
        if not want:
            raise ValueError("Pick a heading from this note.")
        match = next((item for item in sections if item[0].strip().lower() == want), None)
        if match is None:
            match = next((item for item in sections if want in item[0].strip().lower()), None)
        if match is None:
            raise ValueError(f"No heading named {heading!r} in this note.")
        label, start, end = match
        chunk = clamp_slice(source[start:end])
        next_heading = None
        next_offset = None
        has_more = False
        for other_label, other_start, _other_end in sections:
            if other_start >= end:
                next_heading = other_label
                next_offset = other_start
                has_more = True
                break
        if not has_more and start + len(chunk) < len(source):
            has_more = True
            next_offset = start + len(chunk)
        return IncludeSlice(
            text=chunk,
            label=label,
            chars=len(chunk),
            mode="heading",
            offset=start,
            next_offset=next_offset,
            next_heading=next_heading,
            has_more=has_more,
        )

    start = max(0, int(offset or 0))
    if start >= len(source) and source:
        start = 0
    remainder = source[start:]
    chunk = clamp_slice(remainder)
    end = start + len(chunk)
    has_more = end < len(source)
    label = fallback_label
    next_heading = None
    for sec_label, sec_start, sec_end in sections:
        if sec_start <= start < sec_end or (start == 0 and sec_start == 0):
            if sec_label != "Opening":
                label = sec_label
        if has_more and sec_start >= end and next_heading is None:
            next_heading = sec_label
    if start == 0 and not _needs_chunk(source):
        label = fallback_label
        has_more = False
        next_heading = None
    return IncludeSlice(
        text=chunk,
        label=label,
        chars=len(chunk),
        mode="chunk" if has_more or start else ("chunk" if _needs_chunk(source) else "auto"),
        offset=start,
        next_offset=end if has_more else None,
        next_heading=next_heading,
        has_more=has_more,
    )


def format_excerpt(title: str, slice: IncludeSlice) -> str:
    header = f"Title: {(title or 'Untitled').strip()}\nSlice: {slice.chip}"
    if slice.has_more:
        header += "\nHas more: yes — Steve can ask for the next chunk."
    return f"{header}\n\n{slice.text}"


def slice_meta(slice: IncludeSlice) -> dict[str, object]:
    payload: dict[str, object] = {
        "include_chip": slice.chip,
        "include_label": slice.label,
        "include_chars": slice.chars,
        "include_mode": slice.mode,
        "include_offset": slice.offset,
        "include_has_more": slice.has_more,
    }
    if slice.next_offset is not None:
        payload["include_next_offset"] = slice.next_offset
    if slice.next_heading:
        payload["include_next_heading"] = slice.next_heading
    return payload
