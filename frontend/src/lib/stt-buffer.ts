/** One dictation session: committed finals vs uncommitted interim. Never trains per user. */

export function normalizeSpoken(text: string): string {
  return (text || "").replace(/\s+/g, " ").trim();
}

/** Append a final to the field without doubling spaces. */
export function appendSpoken(current: string, piece: string): string {
  const text = (piece || "").trim();
  if (!text) return current || "";
  const before = current || "";
  const padLeft = before && !/\s$/.test(before) ? " " : "";
  return `${before}${padLeft}${text}`;
}

export function foldSpeech(text: string): string {
  return (text || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function lastCommittedSentence(committed: string): string {
  const prev = normalizeSpoken(committed);
  if (!prev) return "";
  const parts = prev.split(/(?<=[.!?])\s+/).filter(Boolean);
  return parts[parts.length - 1] || prev;
}

export function lastCommittedParagraph(committed: string): string {
  const prev = normalizeSpoken(committed);
  if (!prev) return "";
  const parts = prev.split(/(?<=[.!?])\s+/).filter(Boolean);
  const last = parts[parts.length - 1] || prev;
  return last.length >= 40 ? last : lastCommittedSentence(prev);
}

function foldWordOffsets(text: string): number[] {
  const offsets: number[] = [];
  const re = /[a-z0-9]+/gi;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text))) offsets.push(match.index);
  return offsets;
}

function foldedWords(text: string): string[] {
  return foldSpeech(text).split(" ").filter(Boolean);
}

function indexOfWords(hay: string[], needle: string[]): number {
  if (!needle.length || hay.length < needle.length) return -1;
  for (let i = 0; i <= hay.length - needle.length; i += 1) {
    let ok = true;
    for (let j = 0; j < needle.length; j += 1) {
      if (hay[i + j] !== needle[j]) {
        ok = false;
        break;
      }
    }
    if (ok) return i;
  }
  return -1;
}

function removeWordSpan(text: string, start: number, count: number): string {
  const off = foldWordOffsets(text);
  if (start < 0 || !count || start >= off.length) return text.trim();
  const from = off[start];
  const to = off[start + count] ?? text.length;
  return `${text.slice(0, from)}${text.slice(to)}`
    .replace(/[ \t]+/g, " ")
    .replace(/\s+([.,;:])/g, "$1")
    .replace(/\s+\n/g, "\n")
    .trim();
}

function peelFoldedPrefix(incoming: string, prefix: string): string {
  const spoken = incoming.trim();
  const pre = foldedWords(prefix);
  const words = foldedWords(spoken);
  if (!pre.length || words.length < pre.length) return spoken;
  for (let i = 0; i < pre.length; i += 1) {
    if (words[i] !== pre[i]) return spoken;
  }
  return removeWordSpan(spoken, 0, pre.length);
}

function splitOnRepeatedShingles(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  const offsets = foldWordOffsets(trimmed);
  const words = offsets.map((index) => (trimmed.slice(index).match(/^[a-z0-9]+/i)?.[0] || "").toLowerCase());
  if (words.length < 12) return [trimmed];
  const cuts: number[] = [];
  const mark = (i: number) => {
    if (offsets[i] > 0) cuts.push(offsets[i]);
  };

  for (const size of [10, 8, 6]) {
    if (words.length < size * 2) continue;
    const seen = new Map<string, number>();
    for (let i = 0; i <= words.length - size; i += 1) {
      const key = words.slice(i, i + size).join(" ");
      const prev = seen.get(key);
      if (prev !== undefined && i - prev >= size) mark(i);
      if (!seen.has(key)) seen.set(key, i);
    }
  }

  for (const size of [8, 6]) {
    if (words.length < size * 2 + 1) continue;
    const seen = new Map<string, number>();
    for (let i = 0; i <= words.length - (size + 1); i += 1) {
      const key = words.slice(i + 1, i + 1 + size).join(" ");
      const prev = seen.get(key);
      if (prev !== undefined && i - prev >= size) mark(i);
      if (!seen.has(key)) seen.set(key, i);
    }
  }

  if (!cuts.length) return [trimmed];
  const unique = [...new Set(cuts)].sort((a, b) => a - b);
  const chunks: string[] = [];
  let prev = 0;
  for (const cut of unique) {
    const part = trimmed.slice(prev, cut).trim();
    if (part) chunks.push(part);
    prev = cut;
  }
  const last = trimmed.slice(prev).trim();
  if (last) chunks.push(last);
  return chunks;
}

function splitGluedCapitals(line: string): string[] {
  return line
    .split(/(?<=[.!?])\s+(?=[A-Z])/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function splitAtWord(text: string, wordIndex: number): [string, string] {
  const offsets = foldWordOffsets(text);
  if (wordIndex <= 0) return ["", text.trim()];
  if (wordIndex >= offsets.length) return [text.trim(), ""];
  const cut = offsets[wordIndex];
  return [text.slice(0, cut).trim(), text.slice(cut).trim()];
}

/** Split when a later span of the chunk already restates committed corpus (e.g. glued replay). */
function splitIfTailRestatesCorpus(chunk: string, corpus: string): string[] {
  const words = foldedWords(chunk);
  if (words.length < 6 || !foldSpeech(corpus)) return [chunk];
  for (let start = 1; start < words.length; start += 1) {
    if (words.slice(start).join(" ").length < 40) continue;
    const [head, tail] = splitAtWord(chunk, start);
    if (!tail || duplicateRatio(tail, corpus) < 0.55) continue;
    const rest = splitIfTailRestatesCorpus(tail, corpus);
    if (head && /[.!?]$/.test(head.trim())) return [head, ...rest];
    return rest;
  }
  return [chunk];
}

export function joinSpeechChunks(chunks: string[]): string {
  if (!chunks.length) return "";
  let out = chunks[0];
  for (let i = 1; i < chunks.length; i += 1) {
    const chunk = chunks[i];
    const prev = chunks[i - 1];
    const newline =
      /^[-*]\s+/.test(chunk) || /^[-*]\s+/.test(prev) || prev.trim().endsWith(":") || chunk.trim().endsWith(":");
    out = `${out}${newline ? "\n" : " "}${chunk}`;
  }
  return out.trim();
}

export function splitUtterance(text: string): string[] {
  const chunks: string[] = [];
  for (const raw of (text || "").replace(/\r\n/g, "\n").split("\n")) {
    let line = raw.trim();
    if (!line) continue;
    if (/^[-*]\s+/.test(line)) {
      const glued = line.match(/^([-*]\s[\s\S]+?[.!?])\s+([A-Z][\s\S]*)$/);
      if (glued) {
        chunks.push(glued[1].trim());
        line = glued[2].trim();
      } else {
        chunks.push(line);
        continue;
      }
    }
    for (const sentence of splitGluedCapitals(line)) {
      chunks.push(...splitOnRepeatedShingles(sentence));
    }
  }
  return chunks;
}

function wordShingles(folded: string, size: number, skipFirst = false): string[] {
  const words = folded.split(" ").filter(Boolean);
  const start = skipFirst ? 1 : 0;
  if (words.length - start <= size) {
    const slice = words.slice(start).join(" ");
    return slice ? [slice] : [];
  }
  const out: string[] = [];
  for (let i = start; i <= words.length - size; i += 1) out.push(words.slice(i, i + size).join(" "));
  return out;
}

export function duplicateRatio(chunk: string, corpus: string): number {
  const folded = foldSpeech(chunk);
  const have = foldSpeech(corpus);
  if (!folded) return 1;
  if (!have) return 0;
  if (have === folded || have.includes(folded)) return 1;
  const size = folded.length >= 120 ? 6 : 8;
  const score = (shingles: string[]) => {
    if (!shingles.length) return have.includes(folded) ? 1 : 0;
    return shingles.filter((item) => have.includes(item)).length / shingles.length;
  };
  return Math.max(score(wordShingles(folded, size)), score(wordShingles(folded, Math.max(6, size - 2), true)));
}

function bulletsFrom(text: string): string[] {
  return splitUtterance(text)
    .filter((line) => /^[-*]\s+/.test(line) || /^right to\b/i.test(line.trim()))
    .map((line) => foldSpeech(line.replace(/^[-*]\s+/, "")))
    .filter((item) => item.length >= 12);
}

export function isCommaRestatementOfBullets(chunk: string, source: string | string[]): boolean {
  const bullets = Array.isArray(source) ? source : bulletsFrom(source);
  if (bullets.length < 3) return false;
  if (/^[-*]\s+/.test(chunk.trim())) return false;
  const folded = foldSpeech(chunk);
  if (folded.length < 40) return false;
  const hits = bullets.filter((item) => folded.includes(item)).length;
  return hits >= Math.min(3, bullets.length);
}

export function headingsFrom(text: string): string[] {
  const items: string[] = [];
  const seen = new Set<string>();
  const add = (raw: string) => {
    const cleaned = raw.replace(/:+$/, "").trim();
    const words = foldedWords(cleaned);
    if (words.length < 3 || words.length > 8 || foldSpeech(cleaned).length < 10) return;
    const key = words.join(" ");
    if (seen.has(key)) return;
    seen.add(key);
    items.push(cleaned);
  };
  for (const chunk of splitUtterance(text)) {
    const trimmed = chunk.trim();
    if (trimmed.endsWith(":")) add(trimmed);
  }
  const re = /([A-Za-z][A-Za-z0-9' ]{6,70}:)/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(text || ""))) add(match[1]);
  return items;
}

export function stripEmbeddedHeadings(chunk: string, headings: string[]): string {
  let text = chunk.trim();
  for (const heading of headings) {
    const hWords = foldedWords(heading);
    if (hWords.length < 3) continue;
    let guard = 0;
    while (guard < 8) {
      guard += 1;
      const at = indexOfWords(foldedWords(text), hWords);
      if (at <= 0) break;
      text = removeWordSpan(text, at, hWords.length);
    }
  }
  return text.replace(/\s{2,}/g, " ").trim();
}

function alreadyInField(piece: string, fieldValue: string): boolean {
  const spoken = normalizeSpoken(piece);
  const field = normalizeSpoken(fieldValue);
  if (!spoken) return true;
  if (!field) return false;
  return field === spoken || field.endsWith(spoken) || foldSpeech(field).endsWith(foldSpeech(spoken));
}

/** Drop the last 120+ folded chars of source if they reappear anywhere in incoming. */
export function dropRepeatedTail(incoming: string, source: string): string {
  const spoken = incoming.trim();
  const src = foldedWords(source);
  const words = foldedWords(spoken);
  if (!spoken || src.length < 8 || !words.length) return spoken;
  for (let len = src.length; len >= 8; len -= 1) {
    const suffix = src.slice(-len);
    if (suffix.join(" ").length < 120) break;
    const at = indexOfWords(words, suffix);
    if (at === -1) continue;
    return removeWordSpan(spoken, at, suffix.length);
  }
  return spoken;
}

function promoteRightsBullet(chunk: string, bullets: string[]): string {
  const trimmed = chunk.trim();
  if (!bullets.length || /^[-*]\s+/.test(trimmed)) return trimmed;
  if (/^right to\b/i.test(trimmed) && foldSpeech(trimmed).length < 90) return `- ${trimmed}`;
  return trimmed;
}

function absorbNearDuplicate(kept: string[], chunk: string): boolean {
  const folded = foldSpeech(chunk);
  for (let i = kept.length - 1; i >= 0; i -= 1) {
    const prev = kept[i];
    if (duplicateRatio(chunk, prev) < 0.7 && duplicateRatio(prev, chunk) < 0.7) continue;
    if (folded.length > foldSpeech(prev).length) kept[i] = chunk;
    return true;
  }
  return false;
}

/** Collapse restated paragraphs and comma-lists of existing bullets inside one blob. */
export function collapseRestatedSpeech(text: string): string {
  const kept: string[] = [];
  const bullets: string[] = [];
  const headings: string[] = [];
  let corpus = "";
  for (const raw of splitUtterance(text)) {
    for (const piece of splitIfTailRestatesCorpus(raw, corpus)) {
    const chunk = stripEmbeddedHeadings(promoteRightsBullet(piece, bullets), headings);
    const folded = foldSpeech(chunk);
    if (!folded) continue;
    if (isCommaRestatementOfBullets(chunk, bullets)) continue;
    const long = folded.length >= 80;
    const ratio = duplicateRatio(chunk, corpus);
    if (ratio >= 0.55 && absorbNearDuplicate(kept, chunk)) {
      corpus = foldSpeech(kept.join(" "));
      continue;
    }
    if (long && ratio >= 0.55) continue;
    if (!long && ratio >= 0.9) continue;
    if (/^[-*]\s+/.test(chunk)) bullets.push(foldSpeech(chunk.replace(/^[-*]\s+/, "")));
    if (chunk.trim().endsWith(":")) {
      for (const heading of headingsFrom(chunk)) headings.push(heading);
    }
    kept.push(chunk);
    corpus = foldSpeech(kept.join(" "));
    }
  }
  return joinSpeechChunks(kept);
}

function peelCommitted(incoming: string, committed: string): string {
  let rest = peelFoldedPrefix(incoming, committed);
  if (foldSpeech(rest) === foldSpeech(incoming)) {
    rest = peelFoldedPrefix(rest, lastCommittedParagraph(committed));
  }
  if (foldSpeech(rest) === foldSpeech(incoming)) {
    rest = peelFoldedPrefix(rest, lastCommittedSentence(committed));
  }
  return rest;
}

/** Append only text not already committed or sitting at the end of the field. */
export function newFinalSegment(incoming: string, committed: string, fieldValue = ""): string {
  const spoken = normalizeSpoken(incoming);
  if (!spoken) return "";
  const have = committed || "";
  const field = fieldValue || "";
  const prior = `${have}\n${field}`;
  const headings = headingsFrom(prior);

  let rest = collapseRestatedSpeech(incoming);
  rest = stripEmbeddedHeadings(rest, headings);
  rest = peelCommitted(rest, have);
  rest = collapseRestatedSpeech(rest);
  rest = dropRepeatedTail(rest, have);
  rest = dropRepeatedTail(rest, field);
  rest = stripEmbeddedHeadings(rest, headings);

  if (!normalizeSpoken(rest)) return "";

  const extra: string[] = [];
  const haveFold = foldSpeech(`${have} ${field}`);
  const bullets = bulletsFrom(prior);
  for (const chunk of splitUtterance(rest)) {
    const cleaned = stripEmbeddedHeadings(chunk, headings);
    const folded = foldSpeech(cleaned);
    if (!folded) continue;
    if (isCommaRestatementOfBullets(cleaned, bullets)) continue;
    if (folded.length >= 80 && duplicateRatio(cleaned, haveFold) >= 0.55) continue;
    if (folded.length < 80 && (haveFold.includes(folded) || duplicateRatio(cleaned, haveFold) >= 0.9)) continue;
    extra.push(cleaned);
  }
  const out = joinSpeechChunks(extra);
  if (!out) return "";
  if (foldSpeech(out) === foldSpeech(have)) return "";
  if (alreadyInField(out, field)) return "";
  return out;
}
