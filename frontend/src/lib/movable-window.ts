export const ADD_NOTES_POS_KEY = "storykeep-add-notes-pos";
export const COMPOSE_POS_KEY = "storykeep-compose-pos";
export const WINDOW_MARGIN = 8;

export type WindowPoint = { x: number; y: number };

const DRAG_BLOCK =
  "input, textarea, select, option, button, [contenteditable='true'], [role='combobox'], [role='listbox'], [data-no-drag]";

export function parseStoredPoint(raw: string | null): WindowPoint | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as { x?: unknown; y?: unknown };
    if (typeof parsed.x === "number" && typeof parsed.y === "number" && Number.isFinite(parsed.x) && Number.isFinite(parsed.y)) {
      return { x: parsed.x, y: parsed.y };
    }
  } catch {
    /* ignore */
  }
  return null;
}

export function clampWindowPoint(
  x: number,
  y: number,
  w: number,
  h: number,
  vw: number,
  vh: number,
  margin = WINDOW_MARGIN,
): WindowPoint {
  const width = Math.max(1, w);
  const height = Math.max(1, h);
  const maxX = Math.max(margin, vw - width - margin);
  const maxY = Math.max(margin, vh - height - margin);
  return {
    x: Math.min(maxX, Math.max(margin, x)),
    y: Math.min(maxY, Math.max(margin, y)),
  };
}

/** Bottom-left of the viewport so Junior Listen / Word stay clear on the pane. */
export function defaultAddNotesPos(vw: number, vh: number, w: number, h: number): WindowPoint {
  return clampWindowPoint(WINDOW_MARGIN + 8, vh - h - 24, w, h, vw, vh);
}

export function defaultCenteredPos(vw: number, vh: number, w: number, h: number): WindowPoint {
  return clampWindowPoint((vw - w) / 2, (vh - h) / 2, w, h, vw, vh);
}

export function shouldStartWindowDrag(inHandle: boolean, blocked: boolean): boolean {
  return inHandle && !blocked;
}

export function canStartWindowDrag(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  return shouldStartWindowDrag(Boolean(target.closest("[data-drag-handle]")), Boolean(target.closest(DRAG_BLOCK)));
}
