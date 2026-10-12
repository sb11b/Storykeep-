/**
 * Bottom-right placement for the desktop overlay bubble.
 *
 * The overlay is a second Tauri window in the same binary (see
 * `src-tauri/tauri.conf.json`, window label `"overlay"`). Tauri reports
 * monitor geometry in PHYSICAL pixels (`Monitor.position` / `Monitor.size`)
 * while window sizes in the config and in this helper are LOGICAL pixels, so
 * the scale factor converts between the two. Everything here is pure so the
 * placement rules are unit-testable without a desktop.
 */

export interface OverlayMonitorLike {
  /** Top-left corner of the monitor in physical pixels. */
  position: { x: number; y: number };
  /** Monitor size in physical pixels. */
  size: { width: number; height: number };
  /** Device pixel ratio; 1 when absent (tests, older APIs). */
  scaleFactor?: number;
}

export interface OverlayBox {
  width: number;
  height: number;
}

export interface OverlayPoint {
  x: number;
  y: number;
}

/** Gap between the bubble and the monitor edges, in logical pixels. */
export const DEFAULT_OVERLAY_MARGIN = 24;

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

/**
 * Where the overlay window's top-left corner belongs so the bubble sits in the
 * bottom-right of `monitor`, `margin` logical pixels from the edges, and never
 * hangs off the screen. When the monitor is too small to fit the box plus the
 * margin, the box is pinned to the monitor's top-left corner instead — the
 * bubble stays reachable rather than off-screen.
 *
 * The returned point is in PHYSICAL pixels, ready for
 * `getCurrentWindow().setPosition(new PhysicalPosition(x, y))`.
 */
export function computeOverlayPosition(
  monitor: OverlayMonitorLike,
  bubble: OverlayBox,
  margin: number = DEFAULT_OVERLAY_MARGIN,
): OverlayPoint {
  const scale =
    typeof monitor.scaleFactor === "number" && monitor.scaleFactor > 0
      ? monitor.scaleFactor
      : 1;

  const boxWidth = bubble.width * scale;
  const boxHeight = bubble.height * scale;
  const gap = margin * scale;

  const left = monitor.position.x;
  const top = monitor.position.y;
  const right = left + monitor.size.width;
  const bottom = top + monitor.size.height;

  // Prefer bottom-right, but never past the monitor's own edges.
  const maxX = Math.max(left, right - boxWidth);
  const maxY = Math.max(top, bottom - boxHeight);

  return {
    x: Math.round(clamp(right - boxWidth - gap, left, maxX)),
    y: Math.round(clamp(bottom - boxHeight - gap, top, maxY)),
  };
}
