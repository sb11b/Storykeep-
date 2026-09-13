import { createGrokPane, defaultGrokPaneName, type GrokPaneState } from "@/components/grok-pane";

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
    return saved.map((row, index) => ({
      ...createGrokPane(index),
      id: row.id || crypto.randomUUID(),
      displayName: row.displayName?.trim() || defaultGrokPaneName(index),
    }));
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
  return panes.map((pane, index) => ({
    ...pane,
    displayName: labelFromPreferences(labels, index, pane.displayName || defaultGrokPaneName(index)),
  }));
}

export function labelsFromPanes(panes: GrokPaneState[]): Record<string, string> {
  const out: Record<string, string> = {};
  panes.forEach((pane, index) => {
    out[String(index)] = pane.displayName?.trim() || defaultGrokPaneName(index);
  });
  return out;
}
