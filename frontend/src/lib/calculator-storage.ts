import type { AngleMode, CalcHistoryItem } from "@/lib/calculator";
import { CALC_HISTORY_MAX } from "@/lib/calculator";
import { clampCalcBox, defaultCalcSize } from "@/lib/calculator-layout";

export type CalcStored = {
  panel: { x: number; y: number; w: number; h: number };
  history: CalcHistoryItem[];
  angle: AngleMode;
  memory: number;
};

export function calculatorStorageKey(userId: string): string {
  return `storykeep-calculator:${userId || "local"}`;
}

export function emptyCalcStored(vw: number, vh: number): CalcStored {
  const size = defaultCalcSize(vw, vh);
  return {
    panel: { x: Math.max(8, vw - size.w - 24), y: Math.max(8, vh - size.h - 24), w: size.w, h: size.h },
    history: [],
    angle: "deg",
    memory: 0,
  };
}

export function loadCalcStored(userId: string, vw: number, vh: number): CalcStored {
  const fallback = emptyCalcStored(vw, vh);
  try {
    const raw = window.localStorage.getItem(calculatorStorageKey(userId));
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<CalcStored>;
    const panelIn = parsed.panel;
    const panel = clampCalcBox(
      {
        left: typeof panelIn?.x === "number" ? panelIn.x : fallback.panel.x,
        top: typeof panelIn?.y === "number" ? panelIn.y : fallback.panel.y,
        w: typeof panelIn?.w === "number" ? panelIn.w : fallback.panel.w,
        h: typeof panelIn?.h === "number" ? panelIn.h : fallback.panel.h,
      },
      vw,
      vh,
    );
    const history = Array.isArray(parsed.history)
      ? parsed.history
          .filter((item): item is CalcHistoryItem => Boolean(item && typeof item.expr === "string" && typeof item.result === "string"))
          .slice(0, CALC_HISTORY_MAX)
      : [];
    return {
      panel: { x: panel.left, y: panel.top, w: panel.w, h: panel.h },
      history,
      angle: parsed.angle === "rad" ? "rad" : "deg",
      memory: typeof parsed.memory === "number" && Number.isFinite(parsed.memory) ? parsed.memory : 0,
    };
  } catch {
    return fallback;
  }
}

export function saveCalcStored(userId: string, value: CalcStored) {
  try {
    window.localStorage.setItem(calculatorStorageKey(userId), JSON.stringify(value));
  } catch {
    /* ignore quota */
  }
}
