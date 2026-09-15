function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const MEDIA_IMAGE = /!\[([^\]]*)\]\((\/api\/v1\/media\/[0-9a-fA-F-]{36})\)/g;
const HTML_MEDIA_IMG = /<img\b[^>]*\bsrc="(\/api\/v1\/media\/[0-9a-fA-F-]{36})"[^>]*>/gi;
const MEDIA_FILE = /(?<!!)\[([^\]]+)\]\((\/api\/v1\/media\/[0-9a-fA-F-]{36})\)/g;
const MEDIA_LINE = /^(!?\[[^\]]*\]\(\/api\/v1\/media\/[0-9a-fA-F-]{36}\))$/;
const FENCE_OPEN = /^(`{3})([\w-+#.]*)?\s*$/;
const FENCE_CLOSE = /^(`{3})\s*$/;
const INDENTED_CODE = /^(?: {4}|\t)/;
const WIKILINK = /\[\[([^\]|#]+)(?:\|([^\]]+))?\]\]/g;

export type WikilinkResolution = { id: string; title: string };
export type WikilinkResolver = (target: string) => WikilinkResolution | null | undefined;

function renderWikilink(target: string, label: string, resolver?: WikilinkResolver): string {
  const trimmedTarget = target.trim();
  const trimmedLabel = label.trim() || trimmedTarget;
  const resolved = resolver?.(trimmedTarget);
  const escLabel = escapeHtml(trimmedLabel);
  if (resolved) {
    return `<button type="button" class="wikilink" data-wikilink-id="${escapeHtml(resolved.id)}">${escLabel}</button>`;
  }
  return `<button type="button" class="wikilink wikilink-missing" data-wikilink-target="${escapeHtml(trimmedTarget)}">${escLabel}</button>`;
}

function inlineWithWikilinks(value: string, resolver?: WikilinkResolver): string {
  const pieces: string[] = [];
  let cursor = 0;
  for (const match of value.matchAll(WIKILINK)) {
    const index = match.index ?? 0;
    if (index > cursor) pieces.push(escapeHtml(value.slice(cursor, index)));
    pieces.push(renderWikilink(match[1] || "", match[2] || match[1] || "", resolver));
    cursor = index + (match[0]?.length ?? 0);
  }
  pieces.push(escapeHtml(value.slice(cursor)));
  return pieces.join("");
}

function mediaImageHtml(alt: string, url: string): string {
  const id = url.split("/").pop() || "";
  return (
    `<figure class="sk-chat-image">` +
    `<img src="${url}" alt="${alt}" />` +
    `<button type="button" class="sk-chat-image-download" data-media-id="${id}" data-media-url="${url}" aria-label="Download picture">Download picture</button>` +
    `</figure>`
  );
}

const ARTICLE_UUID = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";
const ARTICLE_MD_LINK_SRC = String.raw`\[([^\]]+)\]\((?:(?:\./)?(?:/#article/|#article/|/article/|\?article=))(${ARTICLE_UUID})\)`;
const PUBLISHER_MD_LINK_SRC =
  String.raw`\[([^\]]+)\]\((https?:\/\/(?:www\.)?(?:foxnews\.com|newsmax\.com)[^)\s]*)\)`;

export function articleIdFromHref(href: string | null | undefined): string | null {
  const value = href || "";
  const match = value.match(new RegExp(`(?:#article/|[?&]article=)(${ARTICLE_UUID})`, "i"));
  return match?.[1] || null;
}

export function parseArticleHash(hash: string | null | undefined): string | null {
  const match = (hash || "").match(new RegExp(`^#article/(${ARTICLE_UUID})$`, "i"));
  return match?.[1] || null;
}

export type ChatArticleClick = { kind: "article"; id: string } | { kind: "stay" } | null;

export function chatArticleClick(target: EventTarget | null): ChatArticleClick {
  const el = target as { closest?: (selector: string) => { getAttribute: (name: string) => string | null } | null } | null;
  const node = el?.closest?.("[data-article-id], a[href], button.sk-open-reader");
  if (!node) return null;
  const fromData = node.getAttribute("data-article-id");
  if (fromData && new RegExp(`^${ARTICLE_UUID}$`, "i").test(fromData)) {
    return { kind: "article", id: fromData };
  }
  const href = node.getAttribute("href");
  const fromHref = articleIdFromHref(href);
  if (fromHref) return { kind: "article", id: fromHref };
  if (href) {
    try {
      const url = new URL(href, "https://storykeep.local");
      if (/(^|\.)(foxnews\.com|newsmax\.com)$/i.test(url.hostname)) return { kind: "stay" };
    } catch {
      /* ignore */
    }
  }
  return null;
}

function articleLinkHtml(title: string, id: string): string {
  const safeId = escapeHtml(id);
  return (
    `<a href="#article/${safeId}" class="sk-article-link" data-article-id="${safeId}">${title}</a>` +
    ` <button type="button" class="sk-open-reader" data-article-id="${safeId}">Open in reader</button>`
  );
}

function inline(value: string, resolver?: WikilinkResolver): string {
  const escaped = inlineWithWikilinks(value, resolver)
    .replace(MEDIA_IMAGE, (_all, alt: string, url: string) => mediaImageHtml(alt, url))
    .replace(
      MEDIA_FILE,
      '<a class="sk-attachment-link" href="$2" download="$1">$1</a>',
    )
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
    .replace(/(?<!\w)_([^_\n]+)_(?!\w)/g, "<em>$1</em>")
    .replace(new RegExp(ARTICLE_MD_LINK_SRC, "gi"), (_all, title: string, id: string) => articleLinkHtml(title, id))
    .replace(new RegExp(PUBLISHER_MD_LINK_SRC, "gi"), (_all, title: string) => `<span class="sk-article-title">${title}</span>`)
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

export function wrapWikilink(source: string, start: number, end: number): WrapResult {
  const { from, to } = selectionRange(source, start, end);
  const inner = source.slice(from, to).trim();
  const open = "[[";
  const close = "]]";
  const wrapped = inner ? `${open}${inner}${close}` : `${open}${close}`;
  return {
    text: `${source.slice(0, from)}${wrapped}${source.slice(to)}`,
    selectionStart: from + open.length,
    selectionEnd: from + open.length + inner.length,
  };
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

const CODE_LANGS = ["text", "python", "js", "sql"] as const;
export type CodeLang = (typeof CODE_LANGS)[number];

export function normalizeCodeLang(raw: string | null | undefined): CodeLang {
  const value = (raw || "text").trim().toLowerCase();
  if (value === "javascript" || value === "typescript") return "js";
  if (CODE_LANGS.includes(value as CodeLang)) return value as CodeLang;
  return "text";
}

export function wrapCodeFence(source: string, start: number, end: number, lang: CodeLang = "text"): WrapResult {
  const from = Math.max(0, Math.min(start, end, source.length));
  const to = Math.min(source.length, Math.max(start, end, from));
  if (from === to) {
    const open = `\`\`\`${lang}\n`;
    const fence = `${open}\n\`\`\``;
    const text = `${source.slice(0, from)}${fence}${source.slice(to)}`;
    const caret = from + open.length;
    return { text, selectionStart: caret, selectionEnd: caret };
  }
  const inner = source.slice(from, to);
  const open = `\`\`\`${lang}\n`;
  const close = "\n```";
  const text = `${source.slice(0, from)}${open}${inner}${close}${source.slice(to)}`;
  return {
    text,
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
export function noteMarkdownHtml(source: string, resolver?: WikilinkResolver): string {
  return renderMarkdown(source, resolver);
}

type MarkdownSegment = { kind: "raw"; text: string } | { kind: "highlight"; text: string };

type ParsedBlock = { kind: "code"; lang: string; body: string } | { kind: "text"; lines: string[] };

function renderCodeBlock(lang: string, body: string): string {
  const label = escapeHtml((lang || "text").trim() || "text");
  const escaped = escapeHtml(body);
  return `<pre class="sk-code"><div class="sk-code-bar"><span class="sk-code-lang">${label}</span><button type="button" data-copy>Copy</button></div><code>${escaped}</code></pre>`;
}

function parseBlocks(source: string): ParsedBlock[] {
  const lines = source.split("\n");
  const blocks: ParsedBlock[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index] ?? "";
    const fenceOpen = line.match(FENCE_OPEN);
    if (fenceOpen) {
      const lang = (fenceOpen[2] || "text").trim() || "text";
      index += 1;
      const bodyLines: string[] = [];
      while (index < lines.length && !FENCE_CLOSE.test(lines[index] ?? "")) {
        bodyLines.push(lines[index] ?? "");
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push({ kind: "code", lang, body: bodyLines.join("\n") });
      continue;
    }
    if (INDENTED_CODE.test(line)) {
      const bodyLines: string[] = [];
      while (index < lines.length && INDENTED_CODE.test(lines[index] ?? "")) {
        bodyLines.push((lines[index] ?? "").replace(/^(?: {4}|\t)/, ""));
        index += 1;
      }
      blocks.push({ kind: "code", lang: "text", body: bodyLines.join("\n") });
      continue;
    }
    const textLines: string[] = [];
    while (index < lines.length) {
      const current = lines[index] ?? "";
      if (FENCE_OPEN.test(current) || INDENTED_CODE.test(current)) break;
      textLines.push(current);
      index += 1;
    }
    if (textLines.length) blocks.push({ kind: "text", lines: textLines });
  }
  return blocks.length ? blocks : [{ kind: "text", lines: [] }];
}

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

function renderTextLines(lines: string[], resolver?: WikilinkResolver): string {
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
      html.push(`<h${level}>${inline(heading[2], resolver)}</h${level}>`);
      continue;
    }
    if (MEDIA_LINE.test(line.trim())) {
      flushList();
      html.push(inline(line.trim(), resolver));
      continue;
    }
    const numbered = line.match(/^\d+\.\s+(.*)$/);
    if (numbered) {
      openList("ol");
      html.push(`<li>${inline(numbered[1], resolver)}</li>`);
      continue;
    }
    const bullet = line.match(/^[-*•]\s+(.*)$/);
    if (bullet) {
      openList("ul");
      html.push(`<li>${inline(bullet[1], resolver)}</li>`);
      continue;
    }
    flushList();
    html.push(`<p>${inline(line, resolver)}</p>`);
  }
  flushList();
  return html.join("");
}

function renderMarkdownBlocks(source: string, resolver?: WikilinkResolver): string {
  return parseBlocks(source)
    .map((block) => {
      if (block.kind === "code") return renderCodeBlock(block.lang, block.body);
      return splitHighlightSegments(block.lines.join("\n"))
        .map((segment) => {
          if (segment.kind === "highlight") {
            const inner = renderMarkdownBlocks(segment.text, resolver);
            return inner ? `<mark class="sk-highlight-block">${inner}</mark>` : "";
          }
          return renderTextLines(segment.text.split("\n"), resolver);
        })
        .join("");
    })
    .join("");
}

function htmlMediaImagesToMarkdown(source: string): string {
  return source.replace(HTML_MEDIA_IMG, (tag, url: string) => {
    const alt = (tag.match(/\balt="([^"]*)"/i)?.[1] || "generated image").replace(/]/g, "");
    return `![${alt}](${url})`;
  });
}

export function renderMarkdown(source: string, resolver?: WikilinkResolver): string {
  const normalized = htmlMediaImagesToMarkdown((source || "").replace(/\r\n/g, "\n"));
  return renderMarkdownBlocks(normalized, resolver);
}
