function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const MEDIA_IMAGE = /!\[([^\]]*)\]\((\/api\/v1\/media\/[0-9a-fA-F-]{36})\)/g;
const MEDIA_LINE = /^!\[([^\]]*)\]\((\/api\/v1\/media\/[0-9a-fA-F-]{36})\)$/;

function inline(value: string): string {
  const escaped = escapeHtml(value)
    .replace(MEDIA_IMAGE, '<img src="$2" alt="$1" />')
    .replace(/==([\s\S]+?)==/g, "<mark>$1</mark>")
    .replace(/&lt;u&gt;([\s\S]*?)&lt;\/u&gt;/gi, "<u>$1</u>")
    .replace(
      /&lt;span class=&quot;sk-size-sm&quot;&gt;([\s\S]*?)&lt;\/span&gt;/gi,
      '<span class="sk-size-sm">$1</span>',
    )
    .replace(
      /&lt;span class=&quot;sk-size-lg&quot;&gt;([\s\S]*?)&lt;\/span&gt;/gi,
      '<span class="sk-size-lg">$1</span>',
    );
  return escaped
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
    .replace(/(^|[^_])_([^_]+)_/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
}

function wordAroundCaret(source: string, caret: number): { from: number; to: number } {
  let from = caret;
  let to = caret;
  while (from > 0 && /[^\s]/.test(source[from - 1]!)) from -= 1;
  while (to < source.length && /[^\s]/.test(source[to]!)) to += 1;
  return { from, to };
}

export type WrapResult = { text: string; selectionStart: number; selectionEnd: number };

function selectionRange(source: string, start: number, end: number): { from: number; to: number } {
  let from = Math.max(0, Math.min(start, end, source.length));
  let to = Math.min(source.length, Math.max(start, end, from));
  if (from === to) {
    const word = wordAroundCaret(source, from);
    from = word.from;
    to = word.to;
  }
  return { from, to };
}

export function wrapHighlight(source: string, start: number, end: number): WrapResult {
  return wrapInline(source, start, end, "==", "==");
}

export function wrapInline(source: string, start: number, end: number, open: string, close: string): WrapResult {
  const { from, to } = selectionRange(source, start, end);
  const inner = source.slice(from, to);
  return {
    text: `${source.slice(0, from)}${open}${inner}${close}${source.slice(to)}`,
    selectionStart: from + open.length,
    selectionEnd: from + open.length + inner.length,
  };
}

function lineBounds(source: string, start: number, end: number): { from: number; to: number } {
  const from = source.lastIndexOf("\n", Math.max(0, Math.min(start, end) - 1)) + 1;
  const max = Math.max(start, end);
  const nl = source.indexOf("\n", max);
  const to = nl === -1 ? source.length : nl;
  return { from, to };
}

export function prefixSelectedLines(
  source: string,
  start: number,
  end: number,
  kind: "ul" | "ol",
): WrapResult {
  if (start === end) {
    const { from, to } = lineBounds(source, start, end);
    const line = source.slice(from, to).replace(/^\s*(?:[-*]\s+|\d+\.\s+)?/, "");
    const prefix = kind === "ul" ? "- " : "1. ";
    const nextLine = `${prefix}${line}`;
    return {
      text: `${source.slice(0, from)}${nextLine}${source.slice(to)}`,
      selectionStart: from + prefix.length,
      selectionEnd: from + nextLine.length,
    };
  }
  const { from, to } = lineBounds(source, start, end);
  const block = source.slice(from, to);
  const lines = block.split("\n");
  const next = lines
    .map((line, index) => {
      const body = line.replace(/^\s*(?:[-*]\s+|\d+\.\s+)?/, "");
      return kind === "ul" ? `- ${body}` : `${index + 1}. ${body}`;
    })
    .join("\n");
  return {
    text: `${source.slice(0, from)}${next}${source.slice(to)}`,
    selectionStart: from,
    selectionEnd: from + next.length,
  };
}

/** Render StoryKeep note markdown for reader, filed notes, and preview. */
export function noteMarkdownHtml(source: string): string {
  return renderMarkdown(source);
}

type MarkdownSegment = { kind: "raw"; text: string } | { kind: "highlight"; text: string };

function splitHighlightSegments(source: string): MarkdownSegment[] {
  const segments: MarkdownSegment[] = [];
  const re = /==([\s\S]+?)==/g;
  let last = 0;
  for (const match of source.matchAll(re)) {
    const index = match.index ?? 0;
    if (index > last) segments.push({ kind: "raw", text: source.slice(last, index) });
    const inner = match[1] ?? "";
    if (inner.includes("\n")) {
      segments.push({ kind: "highlight", text: inner });
    } else {
      segments.push({ kind: "raw", text: match[0] ?? "" });
    }
    last = index + (match[0]?.length ?? 0);
  }
  if (last < source.length) segments.push({ kind: "raw", text: source.slice(last) });
  return segments.length ? segments : [{ kind: "raw", text: source }];
}

function renderMarkdownBlocks(source: string): string {
  const lines = source.split("\n");
  const html: string[] = [];
  let listKind: "ul" | "ol" | null = null;
  const flushList = () => {
    if (listKind) {
      html.push(`</${listKind}>`);
      listKind = null;
    }
  };
  const openList = (kind: "ul" | "ol") => {
    if (listKind !== kind) {
      flushList();
      html.push(`<${kind}>`);
      listKind = kind;
    }
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      flushList();
      continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.*)$/);
    if (heading) {
      flushList();
      const level = heading[1].length;
      html.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      continue;
    }
    if (MEDIA_LINE.test(line.trim())) {
      flushList();
      html.push(inline(line.trim()));
      continue;
    }
    const numbered = line.match(/^\d+\.\s+(.*)$/);
    if (numbered) {
      openList("ol");
      html.push(`<li>${inline(numbered[1])}</li>`);
      continue;
    }
    const bullet = line.match(/^[-*•]\s+(.*)$/);
    if (bullet) {
      openList("ul");
      html.push(`<li>${inline(bullet[1])}</li>`);
      continue;
    }
    flushList();
    html.push(`<p>${inline(line)}</p>`);
  }
  flushList();
  return html.join("");
}

export function renderMarkdown(source: string): string {
  const normalized = (source || "").replace(/\r\n/g, "\n");
  return splitHighlightSegments(normalized)
    .map((segment) => {
      if (segment.kind === "highlight") {
        const inner = renderMarkdownBlocks(segment.text);
        return inner ? `<mark class="sk-highlight-block">${inner}</mark>` : "";
      }
      return renderMarkdownBlocks(segment.text);
    })
    .join("");
}
