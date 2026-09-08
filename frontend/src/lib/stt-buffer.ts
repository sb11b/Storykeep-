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

function alreadyInField(piece: string, fieldValue: string): boolean {
  const spoken = normalizeSpoken(piece);
  const field = normalizeSpoken(fieldValue);
  if (!spoken) return true;
  if (!field) return false;
  return field === spoken || field.endsWith(spoken) || field.endsWith(` ${spoken}`);
}

/** Append only text not already committed or sitting at the end of the field. */
export function newFinalSegment(incoming: string, committed: string, fieldValue = ""): string {
  const spoken = normalizeSpoken(incoming);
  if (!spoken) return "";
  const have = normalizeSpoken(committed);
  const field = fieldValue || "";

  if (have) {
    if (spoken === have || have.startsWith(spoken)) return "";
    if (spoken.startsWith(have)) {
      const rest = spoken.slice(have.length).trim();
      return alreadyInField(rest, field) ? "" : rest;
    }
    const last = lastCommittedSentence(have);
    if (last && spoken.startsWith(last)) {
      const rest = spoken.slice(last.length).trim();
      return alreadyInField(rest, field) ? "" : rest;
    }
  }

  if (alreadyInField(spoken, field)) return "";
  return spoken;
}
