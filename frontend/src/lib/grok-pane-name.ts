/** Default chat pane name. The assistant is Larry, not "Grok". */
export const DEFAULT_PANE_NAME = "Larry (the asparagus)";

/** Labels the UI shipped with before the rename; still scrubbed from preferences. */
const LEGACY_DEFAULT_NAMES = ["Grok", "Grok panel"];

export function defaultGrokPaneName(index: number) {
  return index === 0 ? DEFAULT_PANE_NAME : `${DEFAULT_PANE_NAME} ${index + 1}`;
}

/** True for any name that is a default label rather than something Steve typed. */
export function isDefaultPaneName(name: string, index: number): boolean {
  const trimmed = name.trim();
  if (!trimmed) return true;
  if (trimmed === defaultGrokPaneName(index)) return true;
  return LEGACY_DEFAULT_NAMES.some(
    (legacy) => trimmed === legacy || trimmed === `${legacy} ${index + 1}`,
  );
}
