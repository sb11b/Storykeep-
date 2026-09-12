export function spokenTitle(title: string | null | undefined): string {
  const text = (title || "").trim();
  if (!text) return "";
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

export function countWords(text: string | null | undefined): number {
  return (text || "").match(/\S+/g)?.length ?? 0;
}

export function visibleSpeechText(text: string | null | undefined): string {
  return (text || "")
    .replace(/!\[[^\]]*\]\([^)]+\)/g, " ")
    .replace(/==([\s\S]+?)==/g, "$1")
    .replace(/<img\b[^>]*>/gi, " ");
}

/** Plain speakable text from Grok reply markdown (mirrors backend speech_plain). */
export function chatSpeechPlain(markdown: string | null | undefined): string {
  let text = markdown || "";
  text = text.replace(/<img\b[^>]*>/gi, " ");
  text = text.replace(/!\[[^\]]*\]\([^)]+\)/g, " ");
  text = text.replace(/==([\s\S]+?)==/g, "$1");
  text = text.replace(/<script[\s\S]*?<\/script>/gi, " ");
  text = text.replace(/<style[\s\S]*?<\/style>/gi, " ");
  text = text.replace(/<[^>]+>/g, " ");
  return text.replace(/\s+/g, " ").trim();
}

export function chatSpeechScript(markdown: string | null | undefined): { script: string; visibleWordCount: number } {
  const body = chatSpeechPlain(markdown);
  const script = body
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const visibleWordCount = script.match(/\S+/g)?.length ?? 0;
  return { script, visibleWordCount };
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
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

export function wrapHtmlWords(html: string, startIndex: number): string {
  if (typeof window === "undefined" || !html) return html;
  const doc = new DOMParser().parseFromString(`<div id="tts-root">${html}</div>`, "text/html");
  const root = doc.getElementById("tts-root");
  if (!root) return html;
  const index = { value: startIndex };
  const skip = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "IMG", "SVG", "VIDEO", "AUDIO"]);
  const visit = (node: Node) => {
    if (node.nodeType === Node.ELEMENT_NODE && skip.has((node as Element).tagName)) return;
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent || "";
      if (!text.trim() || !node.parentNode) return;
      node.parentNode.replaceChild(wrapTextValue(text, index, doc), node);
      return;
    }
    const children = Array.from(node.childNodes);
    for (const child of children) visit(child);
  };
  visit(root);
  return root.innerHTML;
}

export function wrapPlainWords(text: string, startIndex: number): string {
  const escaped = escapeHtml(visibleSpeechText(text)).replace(/\n/g, "<br/>");
  return wrapHtmlWords(`<p>${escaped}</p>`, startIndex);
}

export function wordIndexFromCaret(root: HTMLElement | null): number | null {
  return wordIndexFromSelection(root);
}

export function wordIndexFromSelection(root: HTMLElement | null): number | null {
  if (!root || typeof window === "undefined") return null;
  const selection = window.getSelection();
  if (!selection || selection.rangeCount === 0) return null;
  const range = selection.getRangeAt(0);
  if (!root.contains(range.startContainer) && !root.contains(range.commonAncestorContainer)) return null;
  const startNode = range.startContainer;
  const startEl = startNode.nodeType === Node.ELEMENT_NODE ? (startNode as Element) : startNode.parentElement;
  if (!startEl) return null;
  const direct = startEl.closest("[data-tts-word]");
  if (direct instanceof HTMLElement && root.contains(direct)) {
    const index = Number(direct.dataset.ttsWord);
    return Number.isFinite(index) ? index : null;
  }
  const scoped = startEl instanceof HTMLElement ? startEl : startEl.parentElement;
  const nested = scoped?.querySelector?.("[data-tts-word]");
  if (nested instanceof HTMLElement && root.contains(nested)) {
    const index = Number(nested.dataset.ttsWord);
    return Number.isFinite(index) ? index : null;
  }
  const words = Array.from(root.querySelectorAll("[data-tts-word]")) as HTMLElement[];
  for (const word of words) {
    let position: number;
    try {
      position = range.comparePoint(word, 0);
    } catch {
      continue;
    }
    if (position === 1 || position === 0) {
      const index = Number(word.dataset.ttsWord);
      if (Number.isFinite(index)) return index;
    }
  }
  const last = words[words.length - 1];
  if (last) {
    const index = Number(last.dataset.ttsWord);
    if (Number.isFinite(index)) return index;
  }
  return null;
}
