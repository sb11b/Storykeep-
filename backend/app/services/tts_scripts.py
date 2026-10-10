"""Speech-script building for TTS (titles, article/note scripts, section maps, chunking) extracted from tts."""

from __future__ import annotations

import re

from app.models import Article

MAX_CHUNK_CHARS = 1400
NOTES_HARD_CAP = 60_000
COMPOSED_GUID_PREFIX = "storykeep-note:"
IMAGE_MD = re.compile(r"!\[[^\]]*\]\([^)]+\)")
HIGHLIGHT_MD = re.compile(r"==([\s\S]+?)==")
HTML_IMG = re.compile(r"(?is)<img\b[^>]*>")

def spoken_title(title: str | None) -> str:
    text = (title or "").strip()
    if not text:
        return ""
    if text[-1] in ".!?":
        return text
    return text + "."


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def is_composed_note(article: Article) -> bool:
    return (getattr(article, "guid", None) or "").startswith(COMPOSED_GUID_PREFIX)


def note_source_markdown(article: Article) -> str:
    """StoryKeep-authored markdown. Never reads vault files from disk."""
    body = (article.content_text or "").strip()
    if body:
        return body
    for row in getattr(article, "overlay_additions", None) or []:
        markdown = (getattr(row, "markdown", None) or "").strip()
        if markdown:
            return markdown
    return (article.summary or "").strip()


def visible_speech_script(
    visible_text: str,
    *,
    include_notes: bool = False,
    notes_text: str | None = None,
) -> str:
    """Speech script from client-visible reader text only."""
    parts: list[str] = []
    body = speech_plain(visible_text)
    if body:
        parts.append(body)
    if include_notes:
        note_body = speech_plain(notes_text or "")
        if note_body:
            parts.append("Your notes.")
            parts.append(note_body)
    script = "\n\n".join(part for part in parts if part)
    script = re.sub(r"https?://\S+", "", script)
    script = re.sub(r"[ \t]+\n", "\n", script)
    script = re.sub(r"\n{3,}", "\n\n", script).strip()
    if len(script) > NOTES_HARD_CAP:
        script = script[: NOTES_HARD_CAP - 32].rsplit(" ", 1)[0].strip() + " Further notes were omitted."
    return script


def article_script(
    article: Article,
    section_id: str | None = None,
    *,
    include_notes: bool = False,
    extra_notes: list[tuple[str, str]] | None = None,
) -> str:
    parts: list[str] = []
    title = spoken_title(article.title)
    if title and not section_id:
        parts.append(title)
    body = ""
    if section_id:
        for section in body_sections(article):
            if section["id"] == section_id:
                body = speech_plain(section["markdown"])
                heading = spoken_title(section["title"])
                if heading:
                    parts.append(heading)
                break
    elif is_composed_note(article):
        body = speech_plain(note_source_markdown(article))
    else:
        if (article.content_text or "").strip():
            body = speech_plain(article.content_text or "")
        elif article.content_html:
            body = speech_plain(article.content_html)
        else:
            body = speech_plain(article.summary or "")
    if body:
        parts.append(body)
    if include_notes and extra_notes:
        spoken_notes: list[str] = []
        used = len("\n\n".join(parts))
        for note_title, markdown in extra_notes:
            piece = speech_plain(markdown)
            if not piece:
                continue
            header = spoken_title(note_title)
            block = f"{header} {piece}".strip() if header else piece
            if used + len(block) + 28 > NOTES_HARD_CAP:
                spoken_notes.append("Further notes were omitted.")
                break
            spoken_notes.append(block)
            used += len(block) + 2
        if spoken_notes:
            parts.append("Your notes.")
            parts.extend(spoken_notes)
    script = "\n\n".join(part for part in parts if part)
    script = re.sub(r"https?://\S+", "", script)
    script = re.sub(r"[ \t]+\n", "\n", script)
    script = re.sub(r"\n{3,}", "\n\n", script).strip()
    if len(script) > NOTES_HARD_CAP:
        script = script[: NOTES_HARD_CAP - 32].rsplit(" ", 1)[0].strip() + " Further notes were omitted."
    return script


def section_start_words(article: Article) -> dict[str, int]:
    """Word index in the full spoken script where each markdown section begins."""
    sections = body_sections(article)
    title = spoken_title(article.title)
    offset = word_count(title) if title else 0
    starts: dict[str, int] = {}
    for section in sections:
        starts[section["id"]] = offset
        offset += word_count(speech_plain(section["markdown"]))
    return starts


def body_sections(article: Article) -> list[dict[str, str]]:
    raw = note_source_markdown(article) if is_composed_note(article) else (article.content_text or "")
    if not raw.strip():
        raw = speech_plain(article.content_html or article.summary or "")
    blocks = re.split(r"(?m)(?=^#{1,3}\s+)", raw)
    sections: list[dict[str, str]] = []
    for block in blocks:
        text = block.strip()
        if not text:
            continue
        first = text.splitlines()[0]
        heading = re.match(r"^#{1,3}\s+(.*)$", first)
        title = heading.group(1).strip() if heading else first[:80]
        sections.append({"id": str(len(sections)), "title": title[:80], "markdown": text})
    if not sections:
        sections.append({"id": "0", "title": article.title or "Full text", "markdown": raw})
    return sections


def split_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    paragraphs = re.split(r"\n{2,}", text)
    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) > max_chars:
            if buf:
                chunks.append(buf)
                buf = ""
            chunks.extend(_split_long(para, max_chars))
            continue
        candidate = f"{buf}\n\n{para}" if buf else para
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            chunks.append(buf)
            buf = para
    if buf:
        chunks.append(buf)
    return chunks


def _strip_markup(value: str) -> str:
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", value)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def speech_plain(value: str) -> str:
    """Visible words only: drop images and ==highlight== markers, keep the inner text."""
    text = value or ""
    text = HTML_IMG.sub(" ", text)
    text = IMAGE_MD.sub(" ", text)
    text = HIGHLIGHT_MD.sub(r"\1", text)
    return _strip_markup(text)


def _split_long(text: str, max_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    buf = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if buf:
                chunks.append(buf)
                buf = ""
            for i in range(0, len(sentence), max_chars):
                chunks.append(sentence[i : i + max_chars])
            continue
        candidate = f"{buf} {sentence}".strip() if buf else sentence
        if len(candidate) <= max_chars:
            buf = candidate
        else:
            chunks.append(buf)
            buf = sentence
    if buf:
        chunks.append(buf)
    return chunks
