import { createGrokPane, type GrokPaneState } from "@/components/grok-pane";
import { asFilingDestination } from "@/lib/destinations";
import { defaultGrokPaneName, isDefaultPaneName } from "@/lib/grok-pane-name";
import type { PendingAttachment } from "@/lib/larry-attach";

const GROK_PANES_KEY = "storykeep-grok-panes";
const FOLDER_ID = /^[0-9a-fA-F-]{36}$/;

type SavedPaneMeta = {
  id: string;
  displayName: string;
  noteDest?: string;
  noteFolderId?: string | null;
  conversationId?: string | null;
  workingNoteId?: string | null;
  workingNoteTitle?: string | null;
  pendingAttachments?: PendingAttachment[];
};

export function sanitizePendingAttachments(raw: unknown): PendingAttachment[] {
  if (!Array.isArray(raw)) return [];
  const out: PendingAttachment[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const row = item as Record<string, unknown>;
    const id = typeof row.id === "string" ? row.id.trim() : "";
    if (!FOLDER_ID.test(id)) continue;
    const name = typeof row.name === "string" && row.name.trim() ? row.name.trim() : "file";
    const kind = row.kind === "image" ? "image" : "file";
    const contentType = typeof row.content_type === "string" ? row.content_type : "application/octet-stream";
    const size = Number(row.size) || 0;
    const extract = typeof row.extract_text === "string" ? row.extract_text : null;
    out.push({
      id,
      name,
      size,
      url: `/api/v1/media/${id}`,
      kind,
      content_type: contentType,
      extract_text: extract,
    });
    if (out.length >= 5) break;
  }
  return out;
}

/** Load pane shells from localStorage (stable ids + display names + last filing). */
export function loadSavedGrokPanes(): GrokPaneState[] | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(GROK_PANES_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw) as SavedPaneMeta[];
    if (!Array.isArray(saved) || !saved.length) return null;
    return saved.map((row, index) => {
      const stored = row.displayName?.trim() || "";
      const folderId = typeof row.noteFolderId === "string" && FOLDER_ID.test(row.noteFolderId) ? row.noteFolderId : null;
      const conversationId =
        typeof row.conversationId === "string" && FOLDER_ID.test(row.conversationId) ? row.conversationId : null;
      const workingNoteId =
        typeof row.workingNoteId === "string" && FOLDER_ID.test(row.workingNoteId) ? row.workingNoteId : null;
      return {
        ...createGrokPane(index),
        id: row.id || crypto.randomUUID(),
        // A stored legacy "Grok" / "Larry" label upgrades to Junior.
        displayName: isDefaultPaneName(stored, index) ? defaultGrokPaneName(index) : stored,
        noteDest: asFilingDestination(row.noteDest, "notes"),
        noteFolderId: folderId,
        conversationId,
        workingNoteId,
        workingNoteTitle: workingNoteId && typeof row.workingNoteTitle === "string" ? row.workingNoteTitle : null,
        pendingAttachments: sanitizePendingAttachments(row.pendingAttachments),
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
      noteDest: pane.noteDest,
      noteFolderId: pane.noteFolderId,
      conversationId: pane.conversationId,
      workingNoteId: pane.workingNoteId,
      workingNoteTitle: pane.workingNoteTitle,
      pendingAttachments: sanitizePendingAttachments(pane.pendingAttachments),
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
