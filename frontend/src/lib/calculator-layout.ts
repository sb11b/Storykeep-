import { clampWindowPoint } from "@/lib/movable-window";

export const CALC_MIN_W = 300;
export const CALC_MIN_H = 420;
export const CALC_MARGIN = 8;
export const CALC_DEFAULT_W = 360;
export const CALC_DEFAULT_H = 580;

export type CalcBox = { left: number; top: number; w: number; h: number };
export type CalcResizeEdge = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

export function defaultCalcSize(vw: number, vh: number) {
  return {
    w: Math.min(CALC_DEFAULT_W, Math.max(CALC_MIN_W, vw - CALC_MARGIN * 2)),
    h: Math.min(CALC_DEFAULT_H, Math.max(CALC_MIN_H, vh - CALC_MARGIN * 2)),
  };
}

export function defaultCalcBubblePos(vw: number, vh: number) {
  // Sit left of Junior's default bottom-right bubble so they are not stacked.
  return clampWindowPoint(vw - 72 - 64, vh - 72, 56, 56, vw, vh, CALC_MARGIN);
}

export function clampCalcBox(box: CalcBox, vw: number, vh: number): CalcBox {
  const maxW = Math.max(CALC_MIN_W, vw - CALC_MARGIN * 2);
  const maxH = Math.max(CALC_MIN_H, vh - CALC_MARGIN * 2);
  const w = Math.min(maxW, Math.max(CALC_MIN_W, box.w));
  const h = Math.min(maxH, Math.max(CALC_MIN_H, box.h));
  const left = Math.min(Math.max(CALC_MARGIN, vw - w - CALC_MARGIN), Math.max(CALC_MARGIN, box.left));
  const top = Math.min(Math.max(CALC_MARGIN, vh - h - CALC_MARGIN), Math.max(CALC_MARGIN, box.top));
  return { left, top, w, h };
}

export function applyCalcResize(
  start: CalcBox,
  edge: CalcResizeEdge,
  dx: number,
  dy: number,
  vw: number,
  vh: number,
): CalcBox {
  const maxW = Math.max(CALC_MIN_W, vw - CALC_MARGIN * 2);
  const maxH = Math.max(CALC_MIN_H, vh - CALC_MARGIN * 2);
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
    w = Math.min(maxW, Math.max(CALC_MIN_W, start.w - dx));
    left = start.left + start.w - w;
  } else {
    w = Math.min(maxW, Math.max(CALC_MIN_W, w));
  }
  if (north) {
    h = Math.min(maxH, Math.max(CALC_MIN_H, start.h - dy));
    top = start.top + start.h - h;
  } else {
    h = Math.min(maxH, Math.max(CALC_MIN_H, h));
  }
  return clampCalcBox({ left, top, w, h }, vw, vh);
}
