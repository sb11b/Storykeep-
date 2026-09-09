const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "NOSCRIPT"]);

export function matchOffsets(text: string, query: string): { start: number; end: number }[] {
  const needle = query.trim();
  if (!needle) return [];
  const lower = text.toLowerCase();
  const q = needle.toLowerCase();
  const hits: { start: number; end: number }[] = [];
  let from = 0;
  while (from < text.length) {
    const idx = lower.indexOf(q, from);
    if (idx === -1) break;
    hits.push({ start: idx, end: idx + needle.length });
    from = idx + Math.max(needle.length, 1);
  }
  return hits;
}

export function clearFindMarks(root: HTMLElement): void {
  root.querySelectorAll("mark.find-hit").forEach((mark) => {
    const parent = mark.parentNode;
    if (!parent) return;
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
    parent.removeChild(mark);
  });
  root.normalize();
}

export function findMarksInArticle(root: HTMLElement, query: string): HTMLElement[] {
  clearFindMarks(root);
  const needle = query.trim();
  if (!needle) return [];

  const doc = root.ownerDocument;
  const marks: HTMLElement[] = [];
  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent) return NodeFilter.FILTER_REJECT;
      if (parent.closest("mark.find-hit")) return NodeFilter.FILTER_REJECT;
      if (SKIP_TAGS.has(parent.tagName)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });

  const textNodes: Text[] = [];
  let node = walker.nextNode();
  while (node) {
    textNodes.push(node as Text);
    node = walker.nextNode();
  }

  for (const textNode of textNodes) {
    const hits = matchOffsets(textNode.textContent || "", needle);
    for (let i = hits.length - 1; i >= 0; i -= 1) {
      const { start, end } = hits[i]!;
      const mark = doc.createElement("mark");
      mark.className = "find-hit";
      const tail = textNode.splitText(start);
      tail.splitText(end - start);
      tail.parentNode?.insertBefore(mark, tail);
      mark.appendChild(tail);
      marks.push(mark);
    }
  }

  return marks;
}

export function focusFindMark(marks: HTMLElement[], index: number): void {
  const total = marks.length;
  if (!total) return;
  const active = ((index % total) + total) % total;
  marks.forEach((mark, i) => {
    mark.classList.toggle("find-hit-active", i === active);
  });
  marks[active]?.scrollIntoView({ block: "center", behavior: "smooth" });
}
