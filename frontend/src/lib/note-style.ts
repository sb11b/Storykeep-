import type { WrapResult } from "@/lib/markdown";

export type BlockStyle = "body" | "h1" | "h2" | "h3";
/** Point size applied to a selection, e.g. "12" = 12pt. "normal" clears the size. */
export type FontPointSize = "8" | "10" | "12" | "14" | "16" | "18" | "20" | "24" | "normal";

export type ComposerStyle = BlockStyle | FontPointSize;

export const COMPOSER_STYLE_OPTIONS: { value: ComposerStyle; label: string }[] = [
  { value: "body", label: "Body" },
  { value: "8", label: "8 pt" },
  { value: "10", label: "10 pt" },
  { value: "12", label: "12 pt" },
  { value: "14", label: "14 pt" },
  { value: "16", label: "16 pt" },
  { value: "18", label: "18 pt" },
  { value: "20", label: "20 pt" },
  { value: "24", label: "24 pt" },
  { value: "normal", label: "Normal" },
  { value: "h1", label: "Heading 1" },
  { value: "h2", label: "Heading 2" },
  { value: "h3", label: "Heading 3" },
];

const HEADING_PREFIX = /^(#{1,3})\s+/;
const LIST_PREFIX = /^\s*(?:[-*]\s+|\d+\.\s+)/;
const SIZE_CLOSE = "</span>";
/** Matches any sk-size span: legacy sm/lg classes or point sizes (sk-size-12). */
const SIZE_PATTERN = /<span class="sk-size-(?:sm|lg|\d+)">([\s\S]*?)<\/span>/gi;

function lineBounds(source: string, start: number, end: number): { from: number; to: number } {
  const from = source.lastIndexOf("\n", Math.max(0, Math.min(start, end) - 1)) + 1;
  const max = Math.max(start, end);
  const nl = source.indexOf("\n", max);
  const to = nl === -1 ? source.length : nl;
  return { from, to };
}

function blockBounds(source: string, start: number, end: number): { from: number; to: number } {
  const anchorStart = Math.min(start, end);
  const anchorEnd = Math.max(start, end);
  const from = source.lastIndexOf("\n", Math.max(0, anchorStart - 1)) + 1;
  const endNl = source.indexOf("\n", anchorEnd);
  const to = endNl === -1 ? source.length : endNl;
  if (anchorStart === anchorEnd) return { from, to };
  const blockEndNl = source.indexOf("\n", anchorEnd);
  return { from, to: blockEndNl === -1 ? source.length : blockEndNl };
}

function stripLinePrefix(line: string): string {
  return line.replace(LIST_PREFIX, "").replace(HEADING_PREFIX, "");
}

function formatLine(line: string, style: BlockStyle): string {
  const body = stripLinePrefix(line);
  if (style === "body") return body;
  const hashes = style === "h1" ? "#" : style === "h2" ? "##" : "###";
  return `${hashes} ${body}`;
}

export function applyBlockStyle(source: string, start: number, end: number, style: BlockStyle): WrapResult {
  const { from, to } = blockBounds(source, start, end);
  const block = source.slice(from, to);
  const lines = block.split("\n");
  const nextLines = lines.map((line) => formatLine(line, style));
  const nextBlock = nextLines.join("\n");
  return {
    text: `${source.slice(0, from)}${nextBlock}${source.slice(to)}`,
    selectionStart: from,
    selectionEnd: from + nextBlock.length,
  };
}

/** Remove every sk-size span wrapper (sm, lg, and point sizes) from a fragment. */
export function stripSizeSpans(value: string): string {
  return value.replace(SIZE_PATTERN, "$1");
}

export function applyInlineSize(source: string, start: number, end: number, size: FontPointSize): WrapResult {
  let from = Math.max(0, Math.min(start, end, source.length));
  let to = Math.min(source.length, Math.max(start, end, from));
  if (from === to) {
    const bounds = lineBounds(source, from, to);
    from = bounds.from;
    to = bounds.to;
  }
  const inner = stripSizeSpans(source.slice(from, to));
  if (size === "normal") {
    return {
      text: `${source.slice(0, from)}${inner}${source.slice(to)}`,
      selectionStart: from,
      selectionEnd: from + inner.length,
    };
  }
  const open = `<span class="sk-size-${size}">`;
  const wrapped = `${open}${inner}${SIZE_CLOSE}`;
  return {
    text: `${source.slice(0, from)}${wrapped}${source.slice(to)}`,
    selectionStart: from + open.length,
    selectionEnd: from + open.length + inner.length,
  };
}

export function applyComposerStyle(source: string, start: number, end: number, style: ComposerStyle): WrapResult {
  if (style === "normal" || /^\d+$/.test(style)) {
    return applyInlineSize(source, start, end, style as FontPointSize);
  }
  if (style === "body") {
    const block = applyBlockStyle(source, start, end, "body");
    return applyInlineSize(block.text, block.selectionStart, block.selectionEnd, "normal");
  }
  return applyBlockStyle(source, start, end, style as BlockStyle);
}

/** True when the style is a point size (or "normal"). */
export function isPointStyle(style: ComposerStyle): style is FontPointSize {
  return style === "normal" || /^\d+$/.test(style);
}

export function detectComposerStyle(source: string, start: number, end: number): ComposerStyle {
  const { from, to } = lineBounds(source, start, end);
  const line = source.slice(from, to);
  const heading = line.match(/^(#{1,3})\s+/);
  if (heading) {
    const level = heading[1].length;
    if (level === 1) return "h1";
    if (level === 2) return "h2";
    return "h3";
  }
  const slice = source.slice(from, to);
  const sizeMatch = slice.match(/<span class="sk-size-(\d+)"/i);
  if (sizeMatch) return sizeMatch[1] as FontPointSize;
  if (/<span class="sk-size-sm">/i.test(slice)) return "12";
  if (/<span class="sk-size-lg">/i.test(slice)) return "18";
  return "body";
}
