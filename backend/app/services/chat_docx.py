from __future__ import annotations

import io
import re
from zipfile import ZipFile

from docx import Document
from docx.oxml.ns import qn
from docx.shared import Inches, Pt

from app.services.vault_paths import windows_safe_component

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DEFAULT_FILENAME = "junior-note.docx"
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_UL = re.compile(r"^[-*+]\s+(.*)$")
_OL = re.compile(r"^\d+[.)]\s+(.*)$")
_FENCE = re.compile(r"^```")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_CODE = re.compile(r"`([^`]+)`")
_REF_HEAD = re.compile(r"^references?\b", re.I)
_INLINE = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)")


def visible_reply_text(content: str) -> str:
    text = (content or "").replace("\r\n", "\n").strip()
    if not text:
        return ""
    text = _IMAGE.sub("", text)
    text = _LINK.sub(r"\1", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def first_heading(content: str) -> str | None:
    for raw in visible_reply_text(content).split("\n"):
        heading = _HEADING.match(raw.strip())
        if not heading:
            continue
        line = _CODE.sub(r"\1", _BOLD.sub(r"\1", _ITALIC.sub(r"\1", heading.group(2).strip())))
        line = " ".join(line.split())
        if line:
            return line[:120]
    return None


def docx_title(content: str) -> str:
    heading = first_heading(content)
    if heading:
        return heading
    for raw in visible_reply_text(content).split("\n"):
        line = raw.strip()
        if not line or _FENCE.match(line):
            continue
        line = _CODE.sub(r"\1", _BOLD.sub(r"\1", _ITALIC.sub(r"\1", line)))
        line = " ".join(line.split())
        if line:
            return line[:120]
    return "Junior reply"


def docx_filename(content: str) -> str:
    heading = first_heading(content)
    if not heading:
        return DEFAULT_FILENAME
    stem = windows_safe_component(heading) or "junior-note"
    if stem.lower().endswith(".docx"):
        return stem
    return f"{stem}.docx"


def _set_run_font(run, *, bold: bool = False, italic: bool = False) -> None:
    run.bold = bold
    run.italic = italic
    run.font.name = "Times New Roman"
    run.font.size = Pt(12)
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = run._element.makeelement(qn("w:rFonts"), {})
        rpr.insert(0, fonts)
    fonts.set(qn("w:ascii"), "Times New Roman")
    fonts.set(qn("w:hAnsi"), "Times New Roman")
    fonts.set(qn("w:cs"), "Times New Roman")
    fonts.set(qn("w:eastAsia"), "Times New Roman")


def _add_styled_text(paragraph, text: str, *, heading: bool = False) -> None:
    remaining = text or ""
    index = 0
    for match in _INLINE.finditer(remaining):
        if match.start() > index:
            run = paragraph.add_run(remaining[index : match.start()])
            _set_run_font(run, bold=heading)
        token = match.group(0)
        if token.startswith("**"):
            run = paragraph.add_run(token[2:-2])
            _set_run_font(run, bold=True)
        elif token.startswith("`"):
            run = paragraph.add_run(token[1:-1])
            _set_run_font(run, bold=heading)
        else:
            run = paragraph.add_run(token[1:-1])
            _set_run_font(run, italic=True)
        index = match.end()
    if index < len(remaining):
        run = paragraph.add_run(remaining[index:])
        _set_run_font(run, bold=heading)
    if not paragraph.runs:
        run = paragraph.add_run("")
        _set_run_font(run, bold=heading)
    if heading:
        for run in paragraph.runs:
            run.bold = True


def _apply_page(document: Document) -> None:
    for section in document.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)
    normal = document.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)


def _hanging_indent(paragraph) -> None:
    paragraph.paragraph_format.left_indent = Inches(0.5)
    paragraph.paragraph_format.first_line_indent = Inches(-0.5)


def build_message_docx(content: str) -> bytes:
    text = visible_reply_text(content)
    if not text:
        raise ValueError("That reply has no text to put in Word.")
    document = Document()
    _apply_page(document)
    in_references = False
    in_fence = False
    fence_lines: list[str] = []
    lines = text.split("\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        if _FENCE.match(line.strip()):
            if in_fence:
                paragraph = document.add_paragraph()
                _add_styled_text(paragraph, "\n".join(fence_lines))
                fence_lines = []
                in_fence = False
            else:
                in_fence = True
            index += 1
            continue
        if in_fence:
            fence_lines.append(line)
            index += 1
            continue
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        heading = _HEADING.match(stripped)
        if heading:
            title = heading.group(2).strip()
            in_references = bool(_REF_HEAD.match(_CODE.sub(r"\1", _BOLD.sub(r"\1", title))))
            paragraph = document.add_paragraph()
            _add_styled_text(paragraph, title, heading=True)
            index += 1
            continue
        if _REF_HEAD.match(stripped) and len(stripped) < 40:
            in_references = True
            paragraph = document.add_paragraph()
            _add_styled_text(paragraph, stripped, heading=True)
            index += 1
            continue
        bullet = _UL.match(stripped)
        numbered = _OL.match(stripped)
        paragraph = document.add_paragraph()
        if in_references and not bullet and not numbered:
            _hanging_indent(paragraph)
        if bullet:
            _add_styled_text(paragraph, f"• {bullet.group(1).strip()}")
        elif numbered:
            _add_styled_text(paragraph, stripped)
        else:
            _add_styled_text(paragraph, stripped)
        index += 1
    if in_fence and fence_lines:
        paragraph = document.add_paragraph()
        _add_styled_text(paragraph, "\n".join(fence_lines))
    payload = io.BytesIO()
    document.save(payload)
    data = payload.getvalue()
    if not data.startswith(b"PK"):
        raise ValueError("Could not build that Word file.")
    with ZipFile(io.BytesIO(data)) as archive:
        if "word/document.xml" not in archive.namelist():
            raise ValueError("Could not build that Word file.")
    return data


def document_xml(payload: bytes) -> str:
    with ZipFile(io.BytesIO(payload)) as archive:
        return archive.read("word/document.xml").decode("utf-8")
