export const INCLUDE_TURN_CHAR_CAP = 10_000;
export const INCLUDE_TURN_CHAR_MAX = 12_000;
export const WORKING_NOTE_CHAR_CAP = 80_000;

export type IncludeMode = "auto" | "selection" | "heading" | "chunk";

export type ArticleSection = {
  title: string;
  start: number;
  end: number;
};

export type IncludeSlice = {
  text: string;
  label: string;
  chars: number;
  mode: IncludeMode;
  offset: number;
  nextOffset: number | null;
  nextHeading: string | null;
  hasMore: boolean;
  chip: string;
};

const MD_HEADING = /^(#{1,6})\s+(.+?)\s*$/gm;

export function formatIncludeChip(label: string, chars: number): string {
  const title = (label || "Slice").trim() || "Slice";
  return `§ ${title} (${chars.toLocaleString("en-US")} chars)`;
}

export function parseSections(body: string): ArticleSection[] {
  const text = body || "";
  const matches = [...text.matchAll(MD_HEADING)];
  if (!matches.length) {
    return text ? [{ title: "Opening", start: 0, end: text.length }] : [];
  }
  const sections: ArticleSection[] = [];
  const first = matches[0]!;
  if (first.index && first.index > 0 && text.slice(0, first.index).trim()) {
    sections.push({ title: "Opening", start: 0, end: first.index });
  }
  matches.forEach((match, index) => {
    const start = match.index ?? 0;
    const end = index + 1 < matches.length ? (matches[index + 1]!.index ?? text.length) : text.length;
    sections.push({ title: (match[2] || "Section").trim(), start, end });
  });
  return sections;
}

export function articleNeedsIncludeSlice(body: string | null | undefined, cap = INCLUDE_TURN_CHAR_CAP): boolean {
  return (body || "").length > cap;
}

export function clampIncludeSlice(text: string, cap = INCLUDE_TURN_CHAR_CAP, hardMax = INCLUDE_TURN_CHAR_MAX): string {
  const limit = Math.min(Math.max(1, cap), hardMax);
  if (text.length <= limit) return text;
  let cut = text.slice(0, limit);
  const space = cut.lastIndexOf(" ");
  if (space > limit * 0.6) cut = cut.slice(0, space);
  return cut.trimEnd();
}

export function resolveIncludeSlice(input: {
  body: string;
  mode?: IncludeMode | null;
  selection?: string | null;
  heading?: string | null;
  offset?: number;
  title?: string | null;
  cap?: number;
  hardMax?: number;
}): IncludeSlice {
  const source = input.body || "";
  const mode = input.mode || "auto";
  const fallback = (input.title || "").trim() || "Included";
  const turnCap = input.cap ?? INCLUDE_TURN_CHAR_CAP;
  const ceiling = input.hardMax ?? (input.cap ?? INCLUDE_TURN_CHAR_MAX);
  const clip = (text: string) => clampIncludeSlice(text, turnCap, ceiling);

  if (mode === "selection") {
    const quote = (input.selection || "").replace(/\s+/g, " ").trim();
    const text = clip(quote);
    const found = quote ? source.indexOf(quote.slice(0, Math.min(quote.length, 80))) : -1;
    const start = found >= 0 ? found : 0;
    const end = start + text.length;
    const hasMore = end < source.length;
    let nextHeading: string | null = null;
    if (hasMore) {
      nextHeading = parseSections(source).find((section) => section.start >= end)?.title ?? null;
    }
    return {
      text,
      label: "Selection",
      chars: text.length,
      mode: "selection",
      offset: start,
      nextOffset: hasMore ? end : null,
      nextHeading,
      hasMore,
      chip: formatIncludeChip("Selection", text.length),
    };
  }

  const sections = parseSections(source);
  if (mode === "heading") {
    const want = (input.heading || "").trim().toLowerCase();
    const match =
      sections.find((section) => section.title.toLowerCase() === want) ||
      sections.find((section) => section.title.toLowerCase().includes(want));
    const start = match?.start ?? 0;
    const end = match?.end ?? Math.min(source.length, start + turnCap);
    const text = clip(source.slice(start, end));
    const next = sections.find((section) => section.start >= end);
    const hasMore = Boolean(next) || start + text.length < source.length;
    const label = match?.title || fallback;
    return {
      text,
      label,
      chars: text.length,
      mode: "heading",
      offset: start,
      nextOffset: next?.start ?? (hasMore ? start + text.length : null),
      nextHeading: next?.title ?? null,
      hasMore,
      chip: formatIncludeChip(label, text.length),
    };
  }

  const start = Math.max(0, input.offset || 0);
  const chunk = clip(source.slice(start));
  const end = start + chunk.length;
  const hasMore = end < source.length;
  let label = fallback;
  let nextHeading: string | null = null;
  for (const section of sections) {
    if (section.start <= start && start < section.end && section.title !== "Opening") {
      label = section.title;
    }
    if (hasMore && section.start >= end && !nextHeading) nextHeading = section.title;
  }
  if (start === 0 && source.length <= turnCap) {
    return {
      text: chunk,
      label: fallback,
      chars: chunk.length,
      mode: "auto",
      offset: 0,
      nextOffset: null,
      nextHeading: null,
      hasMore: false,
      chip: formatIncludeChip(fallback, chunk.length),
    };
  }
  return {
    text: chunk,
    label,
    chars: chunk.length,
    mode: "chunk",
    offset: start,
    nextOffset: hasMore ? end : null,
    nextHeading,
    hasMore,
    chip: formatIncludeChip(label, chunk.length),
  };
}

export function readerIncludeContext(root?: HTMLElement | null): { selection: string; heading: string | null } {
  if (typeof window === "undefined") return { selection: "", heading: null };
  const selection = window.getSelection();
  const quote = selection && !selection.isCollapsed ? selection.toString().replace(/\s+/g, " ").trim() : "";
  let heading: string | null = null;
  const articleRoot =
    root ||
    (selection?.rangeCount
      ? (selection.getRangeAt(0).commonAncestorContainer as HTMLElement).closest?.(".article-body")
      : null) ||
    (document.querySelector(".article-body") as HTMLElement | null);
  if (selection && selection.rangeCount && articleRoot) {
    let node: Node | null = selection.getRangeAt(0).startContainer;
    while (node && node !== articleRoot) {
      if (node instanceof HTMLElement && /^H[1-6]$/.test(node.tagName)) {
        heading = node.innerText.replace(/\s+/g, " ").trim();
        break;
      }
      node = node.parentNode;
    }
    if (!heading) {
      const range = selection.getRangeAt(0);
      const walker = document.createTreeWalker(articleRoot, NodeFilter.SHOW_ELEMENT);
      let lastHeading: string | null = null;
      let current: Node | null = walker.currentNode;
      while (current) {
        if (current instanceof HTMLElement && /^H[1-6]$/.test(current.tagName)) {
          lastHeading = current.innerText.replace(/\s+/g, " ").trim();
        }
        if (current === range.startContainer || current.contains(range.startContainer)) break;
        current = walker.nextNode();
      }
      heading = lastHeading;
    }
  }
  return { selection: quote, heading };
}
