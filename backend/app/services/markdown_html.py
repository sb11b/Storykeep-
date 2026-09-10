from __future__ import annotations

import html
import re

FENCE_OPEN = re.compile(r"^(`{3})([\w\-+#.]*)?\s*$")
FENCE_CLOSE = re.compile(r"^(`{3})\s*$")
INDENTED_CODE = re.compile(r"^(?: {4}|\t)")


def markdown_to_html(source: str) -> str:
    text = (source or "").replace("\r\n", "\n")
    if not text.strip():
        return ""
    return _render_markdown_blocks(text)


def _render_code_block(lang: str, body: str) -> str:
    label = html.escape((lang or "text").strip() or "text")
    escaped = html.escape(body)
    return (
        f'<pre class="sk-code"><div class="sk-code-bar">'
        f'<span class="sk-code-lang">{label}</span>'
        f'<button type="button" data-copy>Copy</button></div>'
        f"<code>{escaped}</code></pre>"
    )


def _parse_blocks(source: str) -> list[tuple[str, object]]:
    lines = source.split("\n")
    blocks: list[tuple[str, object]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        fence_open = FENCE_OPEN.match(line)
        if fence_open:
            lang = (fence_open.group(2) or "text").strip() or "text"
            index += 1
            body_lines: list[str] = []
            while index < len(lines) and not FENCE_CLOSE.match(lines[index]):
                body_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            blocks.append(("code", (lang, "\n".join(body_lines))))
            continue
        if INDENTED_CODE.match(line):
            body_lines = []
            while index < len(lines) and INDENTED_CODE.match(lines[index]):
                body_lines.append(re.sub(r"^(?: {4}|\t)", "", lines[index]))
                index += 1
            blocks.append(("code", ("text", "\n".join(body_lines))))
            continue
        text_lines: list[str] = []
        while index < len(lines):
            current = lines[index]
            if FENCE_OPEN.match(current) or INDENTED_CODE.match(current):
                break
            text_lines.append(current)
            index += 1
        if text_lines:
            blocks.append(("text", text_lines))
    if not blocks:
        blocks.append(("text", []))
    return blocks


def _render_markdown_blocks(source: str) -> str:
    parts: list[str] = []
    for kind, payload in _parse_blocks(source):
        if kind == "code":
            lang, body = payload  # type: ignore[misc]
            parts.append(_render_code_block(lang, body))
            continue
        text = "\n".join(payload)  # type: ignore[arg-type]
        last = 0
        for match in re.finditer(r"==([\s\S]+?)==", text):
            if match.start() > last:
                parts.append(_render_text_lines(text[last : match.start()].split("\n")))
            inner = match.group(1)
            if "\n" in inner:
                rendered = _render_markdown_blocks(inner)
                if rendered:
                    parts.append(f'<mark class="sk-highlight-block">{rendered}</mark>')
            else:
                parts.append(_render_text_lines([match.group(0)]))
            last = match.end()
        if last < len(text):
            parts.append(_render_text_lines(text[last:].split("\n")))
    return "".join(parts) or f"<p>{_inline(source)}</p>"


def _render_text_lines(lines: list[str]) -> str:
    blocks: list[str] = []
    list_kind: str | None = None

    def flush_list() -> None:
        nonlocal list_kind
        if list_kind:
            blocks.append(f"</{list_kind}>")
            list_kind = None

    def open_list(kind: str) -> None:
        nonlocal list_kind
        if list_kind != kind:
            flush_list()
            blocks.append(f"<{kind}>")
            list_kind = kind

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            flush_list()
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading:
            flush_list()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            continue
        if _is_image_line(line):
            flush_list()
            blocks.append(_inline(line.strip()))
            continue
        numbered = re.match(r"^\d+\.\s+(.*)$", line)
        if numbered:
            open_list("ol")
            blocks.append(f"<li>{_inline(numbered.group(1))}</li>")
            continue
        bullet = re.match(r"^[-*•]\s+(.*)$", line)
        if bullet:
            open_list("ul")
            blocks.append(f"<li>{_inline(bullet.group(1))}</li>")
            continue
        flush_list()
        blocks.append(f"<p>{_inline(line)}</p>")
    flush_list()
    return "".join(blocks)


IMAGE_SRC = re.compile(r"^/api/v1/media/[0-9a-fA-F-]{36}$")
IMAGE_MD = re.compile(r"!\[([^\]]*)\]\((/api/v1/media/[0-9a-fA-F-]{36})\)")


def _is_image_line(line: str) -> bool:
    match = IMAGE_MD.fullmatch(line.strip())
    return bool(match)


def _inline(value: str) -> str:
    def wikilink(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        label = (match.group(2) or target).strip()
        return f'<span class="wikilink">{html.escape(label)}</span>'

    pieces: list[str] = []
    cursor = 0
    for match in re.finditer(r"\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]", value):
        pieces.append(html.escape(value[cursor : match.start()]))
        pieces.append(wikilink(match))
        cursor = match.end()
    pieces.append(html.escape(value[cursor:]))
    escaped = "".join(pieces)
    escaped = IMAGE_MD.sub(
        lambda match: f'<img src="{match.group(2)}" alt="{html.escape(match.group(1))}" />',
        escaped,
    )
    escaped = re.sub(r"==([\s\S]+?)==", r"<mark>\1</mark>", escaped)
    escaped = re.sub(r"&lt;u&gt;([\s\S]*?)&lt;/u&gt;", r"<u>\1</u>", escaped, flags=re.I)
    escaped = re.sub(
        r'&lt;span class=&quot;sk-size-sm&quot;&gt;([\s\S]*?)&lt;/span&gt;',
        r'<span class="sk-size-sm">\1</span>',
        escaped,
        flags=re.I,
    )
    escaped = re.sub(
        r'&lt;span class=&quot;sk-size-lg&quot;&gt;([\s\S]*?)&lt;/span&gt;',
        r'<span class="sk-size-lg">\1</span>',
        escaped,
        flags=re.I,
    )
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", escaped)
    escaped = re.sub(r"(?<!\w)#([A-Za-z][\w/-]{0,40})", r'<span class="hashtag">#\1</span>', escaped)
    return escaped
