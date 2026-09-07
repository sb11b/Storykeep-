export function spokenTitle(title: string | null | undefined): string {
  const text = (title || "").trim();
  if (!text) return "";
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

export function countWords(text: string | null | undefined): number {
  return (text || "").match(/\S+/g)?.length ?? 0;
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
  const skip = new Set(["SCRIPT", "STYLE", "NOSCRIPT"]);
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
  const escaped = escapeHtml(text).replace(/\n/g, "<br/>");
  return wrapHtmlWords(`<p>${escaped}</p>`, startIndex);
}
