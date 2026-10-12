"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, AudioLines, X } from "lucide-react";
import { currentMonitor, getCurrentWindow } from "@tauri-apps/api/window";
import type { Window as TauriWindow } from "@tauri-apps/api/window";
import { LogicalSize, PhysicalPosition } from "@tauri-apps/api/dpi";
import { computeOverlayPosition, DEFAULT_OVERLAY_MARGIN } from "@/lib/overlay-position";

/**
 * The desktop overlay bubble — a second window in the same StoryKeep binary
 * (see src-tauri/tauri.conf.json, window label "overlay"). It is transparent,
 * always on top and click-through: clicks pass to the app underneath except
 * over the bubble itself, which is the standard Tauri v2 pattern
 * (`setIgnoreCursorEvents`).
 *
 * Dictation and read-aloud are NOT implemented yet — the expanded panel is an
 * honest placeholder (slice 1 of 3).
 */

const BUBBLE_WINDOW = { width: 72, height: 72 };
const PANEL_WINDOW = { width: 268, height: 196 };
const MARGIN = DEFAULT_OVERLAY_MARGIN;

const TERRACOTTA = "#a54a24";
const CREAM = "#f8f3e6";

/** True when the Tauri runtime is present (false in a plain browser). */
function hasTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function activeWindow(): TauriWindow | null {
  if (!hasTauri()) return null;
  try {
    return getCurrentWindow();
  } catch {
    return null;
  }
}

/** Click-through everywhere by default; the bubble opts itself back in. */
async function setClickThrough(ignore: boolean): Promise<void> {
  const win = activeWindow();
  if (!win) return;
  try {
    await win.setIgnoreCursorEvents(ignore);
  } catch {
    /* browser or unsupported platform — the page still renders */
  }
}

/**
 * Park the bubble in the bottom-right of the current monitor, `MARGIN` px from
 * the edges, so it never covers the taskbar. `box` is the size the window
 * should occupy (collapsed bubble or expanded panel) in logical pixels.
 * Any Tauri failure leaves the window where it already is.
 */
async function positionWindow(
  win: TauriWindow,
  box: { width: number; height: number },
): Promise<void> {
  try {
    const monitor = await currentMonitor();
    if (!monitor) return;
    const { x, y } = computeOverlayPosition(
      {
        position: { x: monitor.position.x, y: monitor.position.y },
        size: { width: monitor.size.width, height: monitor.size.height },
        scaleFactor: monitor.scaleFactor,
      },
      box,
      MARGIN,
    );
    // computeOverlayPosition returns physical pixels, matching monitor geometry.
    await win.setPosition(new PhysicalPosition(x, y));
  } catch {
    /* keep the default position */
  }
}

async function resizeWindow(
  win: TauriWindow,
  box: { width: number; height: number },
): Promise<void> {
  try {
    await win.setSize(new LogicalSize(box.width, box.height));
    await positionWindow(win, box);
  } catch {
    /* window stays as-is */
  }
}

export default function OverlayPage() {
  const [expanded, setExpanded] = useState(false);
  const [tauriReady, setTauriReady] = useState(false);
  const hoverRef = useRef(false);

  useEffect(() => {
    const win = activeWindow();
    setTauriReady(win !== null);
    if (!win) return;
    void setClickThrough(true);
    void positionWindow(win, BUBBLE_WINDOW);
    return () => {
      void setClickThrough(false);
    };
  }, []);

  const collapseWindow = useCallback(() => {
    const win = activeWindow();
    setExpanded(false);
    if (!win) return;
    void (async () => {
      await resizeWindow(win, BUBBLE_WINDOW);
      // Restore click-through unless the pointer is still over the bubble.
      await setClickThrough(!hoverRef.current);
    })();
  }, []);

  // Esc collapses the expanded panel.
  useEffect(() => {
    if (!expanded) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") collapseWindow();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded, collapseWindow]);

  const expand = useCallback(() => {
    const win = activeWindow();
    setExpanded(true);
    if (!win) return;
    // The panel is bigger than the bubble: grow the window to it and keep it
    // pinned to the bottom-right corner. The whole window becomes clickable.
    void (async () => {
      await resizeWindow(win, PANEL_WINDOW);
      await setClickThrough(false);
    })();
  }, []);

  const onBubbleEnter = useCallback(() => {
    hoverRef.current = true;
    if (!expanded) void setClickThrough(false);
  }, [expanded]);

  const onBubbleLeave = useCallback(() => {
    hoverRef.current = false;
    if (!expanded) void setClickThrough(true);
  }, [expanded]);

  return (
    <div className="relative h-full w-full overflow-hidden bg-transparent">
      {!expanded && (
        <button
          type="button"
          aria-label="StoryKeep dictation bubble"
          title="Dictation and read-aloud are coming in the next update."
          data-testid="overlay-bubble"
          onClick={expand}
          onMouseEnter={onBubbleEnter}
          onMouseLeave={onBubbleLeave}
          className="absolute left-1/2 top-1/2 flex h-16 w-16 -translate-x-1/2 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full shadow-[0_6px_18px_rgba(24,12,6,0.35)] transition-transform hover:scale-105 active:scale-95"
          style={{ backgroundColor: TERRACOTTA, color: CREAM }}
        >
          <Mic size={26} strokeWidth={2} aria-hidden />
        </button>
      )}

      {expanded && (
        <div className="absolute inset-0 p-3">
          <div
            role="dialog"
            aria-label="StoryKeep overlay"
            data-testid="overlay-panel"
            className="flex h-full w-full flex-col justify-end"
          >
            <div
              className="relative rounded-2xl border p-3 shadow-[0_10px_28px_rgba(24,12,6,0.4)]"
              style={{
                backgroundColor: "rgba(165, 74, 36, 0.96)",
                borderColor: "rgba(248, 243, 230, 0.25)",
                color: CREAM,
              }}
            >
              <button
                type="button"
                aria-label="Collapse overlay"
                onClick={collapseWindow}
                className="absolute right-2 top-2 rounded-full p-1 opacity-80 hover:opacity-100"
                style={{ color: CREAM }}
              >
                <X size={14} aria-hidden />
              </button>

              <p className="pr-6 text-[13px] font-medium leading-snug">
                Dictation and read-aloud are coming in the next update.
              </p>

              <div className="mt-3 flex items-center gap-2">
                <span
                  aria-hidden
                  className="flex h-8 w-8 items-center justify-center rounded-full opacity-40"
                  style={{ backgroundColor: "rgba(248, 243, 230, 0.18)", color: CREAM }}
                >
                  <Mic size={16} />
                </span>
                <span
                  aria-hidden
                  className="flex h-8 w-8 items-center justify-center rounded-full opacity-40"
                  style={{ backgroundColor: "rgba(248, 243, 230, 0.18)", color: CREAM }}
                >
                  <AudioLines size={16} />
                </span>
                <span className="ml-1 text-[11px] opacity-70">Ctrl+Alt+Space to hide</span>
              </div>
            </div>
          </div>

          {/* A click anywhere outside the panel collapses it too. Only
              meaningful inside Tauri, where the transparent window can
              receive that click. */}
          <button
            type="button"
            aria-label="Collapse overlay"
            tabIndex={-1}
            onClick={collapseWindow}
            className="absolute inset-0 cursor-default bg-transparent"
          />
        </div>
      )}

      {!tauriReady && (
        <span className="sr-only">Overlay requires the StoryKeep desktop app.</span>
      )}
    </div>
  );
}
