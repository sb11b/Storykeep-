/** One dictation session: committed finals vs uncommitted interim. Never trains per user. */

export function normalizeSpoken(text: string): string {
  return (text || "").replace(/\s+/g, " ").trim();
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

/** Append only text not already committed or sitting at the end of the field. */
export function newFinalSegment(incoming: string, committed: string, fieldValue = ""): string {
  const spoken = normalizeSpoken(incoming);
  if (!spoken) return "";
  const have = normalizeSpoken(committed);
  const field = fieldValue || "";
  if (have && (spoken === have || have.startsWith(spoken))) return "";

  let rest = spoken;
  if (have) rest = peelPrefix(rest, have);
  const lastPara = lastCommittedParagraph(have);
  if (lastPara && lastPara !== have) rest = peelPrefix(rest, lastPara);
  const last = lastCommittedSentence(have);
  if (last && last !== have && last !== lastPara) rest = peelPrefix(rest, last);

  rest = normalizeSpoken(rest);
  if (!rest || rest === have) return "";
  if (have && have.startsWith(rest)) return "";
  if (alreadyInField(rest, field) || alreadyInField(spoken, field)) return "";
  return rest;
}
