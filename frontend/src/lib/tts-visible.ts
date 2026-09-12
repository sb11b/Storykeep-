/** Visible article-body speech: one plaintext string shared by TTS and word spans. */

export type VisibleSpeechPayload = {
  script: string;
  visibleWordCount: number;
};

export function normalizeVisibleSpeechScript(script: string): string {
  return (script || "")
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "SVG", "IMG", "VIDEO", "AUDIO", "NAV"]);

function normalizeComparable(value: string): string {
  return (value || "").replace(/\s+/g, " ").trim().toLowerCase();
}

function isHiddenElement(el: Element): boolean {
  if (el.closest('[aria-hidden="true"]')) return true;
  if (el instanceof HTMLElement && el.hidden) return true;
  if (typeof window !== "undefined" && el instanceof HTMLElement) {
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return true;
  }
  return false;
}

function shouldSkipElement(el: Element): boolean {
  if (isHiddenElement(el)) return true;
  const tag = el.tagName;
  if (SKIP_TAGS.has(tag)) return true;
  if (el.closest(".sk-code-bar")) return true;
  if (tag === "BUTTON") {
    if (el.classList.contains("wikilink")) return false;
    return true;
  }
  return false;
}

function wrapTextValue(text: string, startIndex: { value: number }, doc: Document): DocumentFragment {
  const frag = doc.createDocumentFragment();
  const parts = text.split(/(\s+)/);
  for (const part of parts) {
    if (!part) continue;
    if (/^\s+$/.test(part)) {
      frag.appendChild(doc.createTextNode(part));
      continue;
    }
    const span = doc.createElement("span");
    span.className = "tts-word";
    span.dataset.ttsWord = String(startIndex.value);
    startIndex.value += 1;
    span.textContent = part;
    frag.appendChild(span);
  }
  return frag;
}

function unwrapExistingWords(root: HTMLElement) {
  root.querySelectorAll(".tts-word").forEach((node) => {
    const parent = node.parentNode;
    if (!parent) return;
    parent.replaceChild(document.createTextNode(node.textContent || ""), node);
    parent.normalize();
  });
}

type WalkState = {
  skipTitle: string | null;
  skipAuthor: string | null;
  titleSkipped: boolean;
  authorSkipped: boolean;
};

function shouldSkipLeadText(text: string, state: WalkState): boolean {
  const norm = normalizeComparable(text);
  if (!state.titleSkipped && state.skipTitle && norm === state.skipTitle) {
    state.titleSkipped = true;
    return true;
  }
  if (!state.authorSkipped && state.skipAuthor && norm === state.skipAuthor) {
    state.authorSkipped = true;
    return true;
  }
  return false;
}

function visitForWrap(node: Node, startIndex: { value: number }, doc: Document, state: WalkState) {
  if (node.nodeType === Node.ELEMENT_NODE) {
    const el = node as Element;
    if (shouldSkipElement(el)) return;
  }
  if (node.nodeType === Node.TEXT_NODE) {
    const text = node.textContent || "";
    if (!text.trim() || !node.parentNode) return;
    const trimmed = text.trim();
    if (shouldSkipLeadText(trimmed, state)) {
      node.textContent = "";
      return;
    }
    node.parentNode.replaceChild(wrapTextValue(text, startIndex, doc), node);
    return;
  }
  const children = Array.from(node.childNodes);
  for (const child of children) visitForWrap(child, startIndex, doc, state);
}

/** Wrap visible words in DOM order; returns word count. */
export function wrapVisibleSpeechNodes(
  root: HTMLElement | null,
  opts?: { skipTitle?: string | null; skipAuthor?: string | null },
): number {
  if (!root || typeof window === "undefined") return 0;
  unwrapExistingWords(root);
  const index = { value: 0 };
  const state: WalkState = {
    skipTitle: opts?.skipTitle ? normalizeComparable(opts.skipTitle) : null,
    skipAuthor: opts?.skipAuthor ? normalizeComparable(opts.skipAuthor) : null,
    titleSkipped: false,
    authorSkipped: false,
  };
  visitForWrap(root, index, root.ownerDocument || document, state);
  return index.value;
}

export function visibleSpeechPlaintext(root: HTMLElement | null): string {
  if (!root) return "";
  const words = Array.from(root.querySelectorAll(".tts-word"))
    .map((node) => node.textContent || "")
    .filter(Boolean);
  return words.join(" ");
}

export function countVisibleSpeechWords(root: HTMLElement | null): number {
  if (!root) return 0;
  return root.querySelectorAll(".tts-word").length;
}

export function buildVisibleSpeechScript(
  body: HTMLElement | null,
  opts?: {
    skipTitle?: string | null;
    skipAuthor?: string | null;
    noteRoots?: HTMLElement[];
    includeNotes?: boolean;
  },
): VisibleSpeechPayload {
  const bodyCount = wrapVisibleSpeechNodes(body, {
    skipTitle: opts?.skipTitle,
    skipAuthor: opts?.skipAuthor,
  });
  const parts: string[] = [];
  const bodyText = visibleSpeechPlaintext(body);
  if (bodyText) parts.push(bodyText);
  let notesCount = 0;
  if (opts?.includeNotes && opts.noteRoots?.length) {
    for (const noteRoot of opts.noteRoots) {
      notesCount += wrapVisibleSpeechNodes(noteRoot);
      const noteText = visibleSpeechPlaintext(noteRoot);
      if (noteText) parts.push(noteText);
    }
  }
  const script = normalizeVisibleSpeechScript(parts.join("\n\n"));
  const visibleWordCount = script.match(/\S+/g)?.length ?? 0;
  return { script, visibleWordCount };
}

export type VisibleSpeechSection = { id: string; title: string; word_offset: number };

export function visibleSpeechSections(body: HTMLElement | null): VisibleSpeechSection[] {
  if (!body) return [];
  const headings = Array.from(body.querySelectorAll("h1, h2, h3"));
  const sections: VisibleSpeechSection[] = [];
  headings.forEach((heading, index) => {
    const word = heading.querySelector("[data-tts-word]") as HTMLElement | null;
    const offset = word ? Number(word.dataset.ttsWord) : NaN;
    if (!Number.isFinite(offset)) return;
    sections.push({
      id: String(index),
      title: (heading.textContent || "").trim().slice(0, 80) || `Section ${index + 1}`,
      word_offset: offset,
    });
  });
  return sections;
}
