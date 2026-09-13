import { createGrokPane, type GrokPaneState } from "@/components/grok-pane";
import { defaultGrokPaneName, isDefaultPaneName } from "@/lib/grok-pane-name";

const GROK_PANES_KEY = "storykeep-grok-panes";

type SavedPaneMeta = {
  id: string;
  displayName: string;
};

/** Load pane shells from localStorage (stable ids + display names). */
export function loadSavedGrokPanes(): GrokPaneState[] | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(GROK_PANES_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw) as SavedPaneMeta[];
    if (!Array.isArray(saved) || !saved.length) return null;
    return saved.map((row, index) => {
      const stored = row.displayName?.trim() || "";
      return {
        ...createGrokPane(index),
        id: row.id || crypto.randomUUID(),
        // A stored legacy "Grok" / "Larry" label upgrades to Junior.
        displayName: isDefaultPaneName(stored, index) ? defaultGrokPaneName(index) : stored,
      };
    });
  } catch {
    return null;
  }
}

export function saveGrokPanes(panes: GrokPaneState[]) {
  if (typeof window === "undefined") return;
  try {
    const payload: SavedPaneMeta[] = panes.map((pane, index) => ({
      id: pane.id,
      displayName: pane.displayName?.trim() || defaultGrokPaneName(index),
    }));
    window.localStorage.setItem(GROK_PANES_KEY, JSON.stringify(payload));
  } catch {
    /* ignore */
  }
}

/** User preferences store labels by pane slot index ("0", "1", …). */
export function labelFromPreferences(
  labels: Record<string, string> | undefined,
  paneIndex: number,
  fallback: string,
): string {
  if (!labels) return fallback;
  const byIndex = labels[String(paneIndex)]?.trim();
  if (byIndex) return byIndex;
  return fallback;
}

export function mergePreferenceLabels(
  panes: GrokPaneState[],
  labels: Record<string, string> | undefined,
): GrokPaneState[] {
  if (!labels || !Object.keys(labels).length) return panes;
  return panes.map((pane, index) => {
    const defaultName = defaultGrokPaneName(index);
    const fromPref = labels[String(index)]?.trim() || "";
    const fromPane = pane.displayName?.trim() || defaultName;
    const prefIsCustom = Boolean(fromPref) && !isDefaultPaneName(fromPref, index);
    const paneIsCustom = !isDefaultPaneName(fromPane, index);
    if (prefIsCustom) return { ...pane, displayName: fromPref };
    if (paneIsCustom) return pane;
    return { ...pane, displayName: defaultName };
  });
}

/** Only persist names Steve typed, never a default label. */
export function labelsFromPanes(panes: GrokPaneState[]): Record<string, string> {
  const out: Record<string, string> = {};
  panes.forEach((pane, index) => {
    const name = pane.displayName?.trim() || defaultGrokPaneName(index);
    if (!isDefaultPaneName(name, index)) out[String(index)] = name;
  });
  return out;
}

export function scrubDefaultPaneLabels(labels: Record<string, string> | undefined): Record<string, string> {
  if (!labels) return {};
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(labels)) {
    const index = Number(key);
    const trimmed = value?.trim();
    if (!trimmed) continue;
    if (!Number.isNaN(index) && isDefaultPaneName(trimmed, index)) continue;
    out[key] = trimmed;
  }
  return out;
}
