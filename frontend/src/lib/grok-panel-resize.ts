export const PANEL_MIN_W = 520;
export const PANEL_MIN_H = 600;
export const PANEL_MARGIN = 8;
export const PANEL_DEFAULT_W = 640;
export const PANEL_DEFAULT_H = 720;

export type PanelBox = { left: number; top: number; w: number; h: number };
export type ResizeEdge = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

export function viewportLimit(vw: number, vh: number) {
  return {
    maxW: Math.max(PANEL_MIN_W, vw - PANEL_MARGIN * 2),
    maxH: Math.max(PANEL_MIN_H, vh - PANEL_MARGIN * 2),
  };
}

export function defaultPanelSize(vw: number, vh: number) {
  const { maxW, maxH } = viewportLimit(vw, vh);
  return { w: Math.min(PANEL_DEFAULT_W, maxW), h: Math.min(PANEL_DEFAULT_H, maxH) };
}

export function clampPanelBox(box: PanelBox, vw: number, vh: number): PanelBox {
  const { maxW, maxH } = viewportLimit(vw, vh);
  const w = Math.min(maxW, Math.max(PANEL_MIN_W, box.w));
  const h = Math.min(maxH, Math.max(PANEL_MIN_H, box.h));
  const left = Math.min(Math.max(PANEL_MARGIN, vw - w - PANEL_MARGIN), Math.max(PANEL_MARGIN, box.left));
  const top = Math.min(Math.max(PANEL_MARGIN, vh - h - PANEL_MARGIN), Math.max(PANEL_MARGIN, box.top));
  return { left, top, w, h };
}

export function applyPanelResize(
  start: PanelBox,
  edge: ResizeEdge,
  dx: number,
  dy: number,
  vw: number,
  vh: number,
): PanelBox {
  const { maxW, maxH } = viewportLimit(vw, vh);
  const east = edge === "e" || edge === "ne" || edge === "se";
  const west = edge === "w" || edge === "nw" || edge === "sw";
  const south = edge === "s" || edge === "se" || edge === "sw";
  const north = edge === "n" || edge === "ne" || edge === "nw";

  let w = start.w;
  let h = start.h;
  let left = start.left;
  let top = start.top;

  if (east) w = start.w + dx;
  if (south) h = start.h + dy;
  if (west) {
    w = Math.min(maxW, Math.max(PANEL_MIN_W, start.w - dx));
    left = start.left + start.w - w;
  } else {
    w = Math.min(maxW, Math.max(PANEL_MIN_W, w));
  }
  if (north) {
    h = Math.min(maxH, Math.max(PANEL_MIN_H, start.h - dy));
    top = start.top + start.h - h;
  } else {
    h = Math.min(maxH, Math.max(PANEL_MIN_H, h));
  }

  return clampPanelBox({ left, top, w, h }, vw, vh);
}
