export const HIGHLIGHT_COLORS = ["yellow", "green", "blue", "pink", "orange"] as const;

export type HighlightColor = (typeof HIGHLIGHT_COLORS)[number];

export type Highlight = {
  id: string;
  quote: string;
  color: string;
  prefix?: string | null;
  suffix?: string | null;
};

export function isHighlightColor(value: string | null | undefined): value is HighlightColor {
  return HIGHLIGHT_COLORS.includes(value as HighlightColor);
}

export function selectionInRoot(root: HTMLElement | null): {
  quote: string;
  prefix: string;
  suffix: string;
  top: number;
  left: number;
} | null {
  if (!root || typeof window === "undefined") return null;
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return null;
  const range = selection.getRangeAt(0);
  if (!root.contains(range.commonAncestorContainer)) return null;
  const quote = selection.toString().replace(/\s+/g, " ").trim();
  if (quote.length < 2) return null;
  const before = document.createRange();
  before.selectNodeContents(root);
  before.setEnd(range.startContainer, range.startOffset);
  const start = before.toString().length;
  const full = root.innerText || root.textContent || "";
  const box = range.getBoundingClientRect();
  return {
    quote,
    prefix: full.slice(Math.max(0, start - 48), start),
    suffix: full.slice(start + quote.length, start + quote.length + 48),
    top: box.top,
    left: box.left + box.width / 2,
  };
}

export function applyHighlights(html: string, highlights: Highlight[]): string {
  if (typeof window === "undefined" || !html || highlights.length === 0) return html;
  const doc = new DOMParser().parseFromString(`<div id="hl-root">${html}</div>`, "text/html");
  const root = doc.getElementById("hl-root");
  if (!root) return html;
  for (const item of highlights) {
    const quote = (item.quote || "").replace(/\s+/g, " ").trim();
    if (!quote) continue;
    wrapQuote(root, quote, item.prefix || "", item.suffix || "", item.color, item.id);
  }
  return root.innerHTML;
}

function wrapQuote(root: HTMLElement, quote: string, prefix: string, suffix: string, color: string, id: string) {
  const text = collectText(root);
  const found = locate(text, quote, prefix, suffix);
  if (!found) return;
  wrapOffsets(root, found.start, found.end, color, id);
}

function locate(text: string, quote: string, prefix: string, suffix: string): { start: number; end: number } | null {
  if (prefix || suffix) {
    const context = flexIndex(text, `${prefix}${quote}${suffix}`);
    if (context) {
      const inner = flexIndex(text.slice(context.start, context.end), quote);
      if (inner) {
        return { start: context.start + inner.start, end: context.start + inner.end };
      }
    }
  }
  return flexIndex(text, quote);
}

function flexIndex(haystack: string, needle: string): { start: number; end: number } | null {
  const want = needle.replace(/\s+/g, " ").trim();
  if (!want) return null;
  const parts = want.split(" ");
  let i = 0;
  while (i < haystack.length) {
    let h = i;
    let matched = true;
    let end = i;
    for (let p = 0; p < parts.length; p += 1) {
      while (h < haystack.length && /\s/.test(haystack[h])) h += 1;
      if (haystack.slice(h, h + parts[p].length) !== parts[p]) {
        matched = false;
        break;
      }
      h += parts[p].length;
      end = h;
      if (p < parts.length - 1) {
        if (h >= haystack.length || !/\s/.test(haystack[h])) {
          matched = false;
          break;
        }
      }
    }
    if (matched) return { start: i, end };
    i += 1;
  }
  return null;
}

function collectText(root: Node): string {
  let out = "";
  const walk = root.ownerDocument!.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node = walk.nextNode();
  while (node) {
    out += node.textContent || "";
    node = walk.nextNode();
  }
  return out;
}

function wrapOffsets(root: HTMLElement, start: number, end: number, color: string, id: string) {
  const doc = root.ownerDocument;
  const walk = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let cursor = 0;
  let node = walk.nextNode() as Text | null;
  const targets: { node: Text; from: number; to: number }[] = [];
  while (node) {
    const raw = node.textContent || "";
    const from = cursor;
    const to = cursor + raw.length;
    if (to > start && from < end) {
      targets.push({
        node,
        from: Math.max(0, start - from),
        to: Math.min(raw.length, end - from),
      });
    }
    cursor = to;
    node = walk.nextNode() as Text | null;
  }
  for (const target of targets.reverse()) {
    if (target.from >= target.to) continue;
    const text = target.node;
    const middle = text.splitText(target.from);
    middle.splitText(target.to - target.from);
    const mark = doc.createElement("mark");
    mark.className = `hl hl-${isHighlightColor(color) ? color : "yellow"}`;
    mark.dataset.highlightId = id;
    middle.parentNode?.insertBefore(mark, middle);
    mark.appendChild(middle);
  }
}
