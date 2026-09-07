from __future__ import annotations

import html
import re


def markdown_to_html(source: str) -> str:
    text = (source or "").replace("\r\n", "\n")
    blocks: list[str] = []
    for raw in text.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            continue
        if _is_image_line(line):
            blocks.append(_inline(line.strip()))
            continue
        blocks.append(f"<p>{_inline(line)}</p>")
    return "".join(blocks) or f"<p>{_inline(text)}</p>"


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
    escaped = re.sub(r"==([^=]+)==", r"<mark>\1</mark>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"(?<!\w)#([A-Za-z][\w/-]{0,40})", r'<span class="hashtag">#\1</span>', escaped)
    return escaped
