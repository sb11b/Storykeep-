/** One dictation session: committed finals vs uncommitted interim. Never trains per user. */

export function normalizeSpoken(text: string): string {
  return (text || "").replace(/\s+/g, " ").trim();
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

  // "That protection is…" vs "Data protection is…" — skip the first word of the window.
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
    .flatMap((part) => part.split(/(?<=[a-z0-9,])\s+(?=[A-Z][a-z])/))
    .map((part) => part.trim())
    .filter(Boolean);
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

function alreadyInField(piece: string, fieldValue: string): boolean {
  const spoken = normalizeSpoken(piece);
  const field = normalizeSpoken(fieldValue);
  if (!spoken) return true;
  if (!field) return false;
  return field === spoken || field.endsWith(spoken);
}

function peelPrefix(incoming: string, prefix: string): string {
  let spoken = normalizeSpoken(incoming);
  const have = normalizeSpoken(prefix);
  if (!spoken || !have || have.length < 2) return spoken;
  let guard = 0;
  while (guard < 32 && spoken.startsWith(have)) {
    guard += 1;
    const rest = spoken.slice(have.length).replace(/^[\s.,;:]+/, "").trim();
    if (!rest) return "";
    if (rest === spoken) break;
    spoken = rest;
  }
  return spoken;
}

function dropFuzzyOverlap(incoming: string, committed: string): string {
  const inf = foldSpeech(incoming);
  const cf = foldSpeech(committed);
  if (!inf) return "";
  if (!cf) return incoming.trim();
  for (let n = Math.min(inf.length, cf.length); n >= 120; n -= 1) {
    if (!inf.startsWith(cf.slice(-n))) continue;
    const parts = splitUtterance(incoming);
    const kept: string[] = [];
    let consumed = 0;
    for (const part of parts) {
      const next = foldSpeech(part);
      consumed += next.length + 1;
      if (consumed <= n + 8) continue;
      kept.push(part);
    }
    return kept.join("\n").trim();
  }
  return incoming.trim();
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
  let corpus = "";
  for (const raw of splitUtterance(text)) {
    const chunk = promoteRightsBullet(raw, bullets);
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
    kept.push(chunk);
    corpus = foldSpeech(kept.join(" "));
  }
  return kept.join("\n").trim();
}

/** Append only text not already committed or sitting at the end of the field. */
export function newFinalSegment(incoming: string, committed: string, fieldValue = ""): string {
  const spoken = normalizeSpoken(incoming);
  if (!spoken) return "";
  const collapsed = collapseRestatedSpeech(incoming);
  const have = committed || "";
  const field = fieldValue || "";

  if (!normalizeSpoken(have)) {
    if (alreadyInField(collapsed, field)) return "";
    return collapsed;
  }

  let rest = peelPrefix(normalizeSpoken(collapsed), normalizeSpoken(have));
  if (normalizeSpoken(rest) === normalizeSpoken(collapsed)) {
    rest = peelPrefix(rest, lastCommittedParagraph(have));
    if (normalizeSpoken(rest) === normalizeSpoken(collapsed)) {
      rest = peelPrefix(rest, lastCommittedSentence(have));
    }
  }
  rest = collapseRestatedSpeech(rest || collapsed);
  rest = dropFuzzyOverlap(rest, have);

  const extra: string[] = [];
  const haveFold = foldSpeech(have);
  const bullets = bulletsFrom(have);
  for (const chunk of splitUtterance(rest)) {
    const folded = foldSpeech(chunk);
    if (!folded) continue;
    if (isCommaRestatementOfBullets(chunk, bullets)) continue;
    if (folded.length >= 80 && duplicateRatio(chunk, have) >= 0.55) continue;
    if (folded.length < 80 && (haveFold.includes(folded) || duplicateRatio(chunk, have) >= 0.9)) continue;
    extra.push(chunk);
  }
  const out = extra.join("\n").trim();
  if (!out) return "";
  if (foldSpeech(out) === haveFold) return "";
  if (alreadyInField(out, field)) return "";
  return out;
}
