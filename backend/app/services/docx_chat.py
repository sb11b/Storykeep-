from __future__ import annotations

import html as html_lib
import io
import re
import zipfile

from lxml import html as lxml_html

DOCX_READ_ERROR = "couldn't read that Word file"
DOC_HINT = "Legacy Word .doc is not supported. Save as .docx and attach again."
MACRO_HINT = "Word macros and embedded objects are not allowed."
OLE_MAGIC = b"\xd0\xcf\x11\xe0"
_ALLOWED_TAGS = frozenset({"p", "h1", "h2", "h3", "ul", "ol", "li", "strong", "em", "a", "br"})
_BLOCK_TAGS = frozenset({"p", "h1", "h2", "h3", "li"})
_HTTPS = re.compile(r"^https://", re.I)


def inspect_docx_bytes(payload: bytes, filename: str | None = None) -> None:
    suffix = ""
    if filename:
        name = filename.replace("\\", "/").rsplit("/", 1)[-1]
        dot = name.rfind(".")
        suffix = name[dot:].lower() if dot >= 0 else ""
    if suffix == ".doc":
        raise ValueError(DOC_HINT)
    if not payload:
        raise ValueError(DOCX_READ_ERROR)
    if payload[:8].startswith(OLE_MAGIC) or payload[:4] == b"\xd0\xcf\x11\xe0":
        raise ValueError(MACRO_HINT)
    if payload[:2] != b"PK":
        raise ValueError(DOCX_READ_ERROR)
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise ValueError(DOCX_READ_ERROR) from exc
    with archive:
        names = [name.replace("\\", "/").lower() for name in archive.namelist()]
        if "word/document.xml" not in names:
            raise ValueError(DOCX_READ_ERROR)
        for name in names:
            if name.endswith("vbaproject.bin") or name.endswith("vbadata.xml"):
                raise ValueError(MACRO_HINT)
            if "/embeddings/" in name or name.startswith("word/embeddings/"):
                raise ValueError(MACRO_HINT)
            if "oleobject" in name:
                raise ValueError(MACRO_HINT)


def sanitize_docx_html(raw: str) -> str:
    fragment = (raw or "").strip()
    if not fragment:
        return ""
    try:
        root = lxml_html.fromstring(f"<div>{fragment}</div>")
    except Exception:
        return ""
    kill: list[lxml_html.HtmlElement] = []
    unwrap: list[lxml_html.HtmlElement] = []
    for el in list(root.iter()):
        if not isinstance(el.tag, str):
            kill.append(el)
            continue
        local = el.tag.lower().split("}", 1)[-1]
        if local in {"script", "iframe", "object", "embed", "style", "img", "svg", "video", "audio"}:
            kill.append(el)
            continue
        if local.startswith("v:") or "bindata" in local.lower() or local.endswith("bindata"):
            kill.append(el)
            continue
        if local == "div":
            continue
        if local not in _ALLOWED_TAGS:
            unwrap.append(el)
            continue
        if local == "a":
            href = (el.get("href") or "").strip()
            el.attrib.clear()
            if _HTTPS.match(href):
                el.set("href", href)
            else:
                unwrap.append(el)
            continue
        el.attrib.clear()
    for el in kill:
        parent = el.getparent()
        if parent is not None:
            el.drop_tree()
    for el in unwrap:
        parent = el.getparent()
        if parent is not None:
            el.drop_tag()
    inner = "".join(
        lxml_html.tostring(child, encoding="unicode") if isinstance(getattr(child, "tag", None), str) else ""
        for child in root
    )
    return inner.strip()


def html_to_plain(html: str) -> str:
    fragment = (html or "").strip()
    if not fragment:
        return ""
    try:
        root = lxml_html.fromstring(f"<div>{fragment}</div>")
    except Exception:
        return re.sub(r"<[^>]+>", " ", fragment).strip()
    lines: list[str] = []

    def walk(node: lxml_html.HtmlElement) -> None:
        if not isinstance(node.tag, str):
            return
        tag = node.tag.lower().split("}", 1)[-1]
        if tag in _BLOCK_TAGS:
            text = " ".join(node.text_content().split())
            if not text:
                return
            if tag == "li":
                lines.append(f"- {text}")
            else:
                lines.append(text)
            return
        for child in node:
            walk(child)

    walk(root)
    return re.sub(r"\n{3,}", "\n\n", "\n\n".join(lines)).strip()


def extract_chat_docx(payload: bytes, filename: str | None = None) -> tuple[str, str]:
    inspect_docx_bytes(payload, filename)
    try:
        import mammoth
        from mammoth import html as mammoth_html
    except Exception as exc:
        raise ValueError(DOCX_READ_ERROR) from exc

    def convert_image(image):
        alt = (getattr(image, "alt_text", None) or "").strip()
        if not alt:
            return []
        return [mammoth_html.element("p", {}, [mammoth_html.text(alt)])]

    try:
        result = mammoth.convert_to_html(io.BytesIO(payload), convert_image=convert_image)
        cleaned = sanitize_docx_html(result.value or "")
        text = html_to_plain(cleaned)
        if not text:
            raw = mammoth.extract_raw_text(io.BytesIO(payload)).value or ""
            text = re.sub(r"\n{3,}", "\n\n", raw).strip()
            if text:
                cleaned = "".join(f"<p>{html_lib.escape(part)}</p>" for part in text.split("\n\n") if part.strip())
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(DOCX_READ_ERROR) from exc
    if not text.strip():
        raise ValueError(DOCX_READ_ERROR)
    return text, cleaned
