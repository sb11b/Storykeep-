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
    .replace(/==([^=]+)==/g, "<mark>$1</mark>");
  return escaped
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
    .replace(/(^|[^_])_([^_]+)_/g, "$1<em>$2</em>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noreferrer">$1</a>');
}

export function wrapHighlight(
  source: string,
  start: number,
  end: number,
): { text: string; selectionStart: number; selectionEnd: number } {
  const from = Math.max(0, Math.min(start, end, source.length));
  const to = Math.min(source.length, Math.max(start, end, from));
  if (from === to) {
    const insert = "==highlighted==";
    return {
      text: source.slice(0, from) + insert + source.slice(to),
      selectionStart: from + 2,
      selectionEnd: from + insert.length - 2,
    };
  }
  const inner = source.slice(from, to);
  return {
    text: `${source.slice(0, from)}==${inner}==${source.slice(to)}`,
    selectionStart: from + 2,
    selectionEnd: from + 2 + inner.length,
  };
}

export function renderMarkdown(source: string): string {
  const lines = (source || "").replace(/\r\n/g, "\n").split("\n");
  const html: string[] = [];
  let inList = false;
  const flushList = () => {
    if (inList) {
      html.push("</ul>");
      inList = false;
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
    const bullet = line.match(/^[-*]\s+(.*)$/);
    if (bullet) {
      if (!inList) {
        html.push("<ul>");
        inList = true;
      }
      html.push(`<li>${inline(bullet[1])}</li>`);
      continue;
    }
    flushList();
    html.push(`<p>${inline(line)}</p>`);
  }
  flushList();
  return html.join("");
}
