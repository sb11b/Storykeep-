/** Default chat pane name. Steve can rename a pane later. */
export const DEFAULT_PANE_NAME = "Junior";

/** Labels the UI shipped with before Junior; still scrubbed from preferences. */
const LEGACY_DEFAULT_NAMES = ["Grok", "Grok panel", "Larry", "Larry (the asparagus)"];

export function defaultGrokPaneName(index: number) {
  return index === 0 ? DEFAULT_PANE_NAME : `${DEFAULT_PANE_NAME} ${index + 1}`;
}

/** True for any name that is a default label rather than something Steve typed. */
export function isDefaultPaneName(name: string, index: number): boolean {
  const trimmed = name.trim();
  if (!trimmed) return true;
  if (trimmed === DEFAULT_PANE_NAME) return true;
  if (trimmed === defaultGrokPaneName(index)) return true;
  return LEGACY_DEFAULT_NAMES.some(
    (legacy) => trimmed === legacy || trimmed === `${legacy} ${index + 1}`,
  );
}

export type ChatStatusKind = "working" | "thinking" | "writing";

export function chatStatusLine(name: string, kind: ChatStatusKind): string {
  const who = name.trim() || DEFAULT_PANE_NAME;
  if (kind === "working") return `${who} is working…`;
  if (kind === "thinking") return `${who} is thinking…`;
  return `${who} is writing…`;
}
