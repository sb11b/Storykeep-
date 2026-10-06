"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  PANEL_MARGIN,
  applyPanelResize,
  clampPanelBox,
  defaultPanelSize,
  type PanelBox,
  type ResizeEdge,
} from "@/lib/grok-panel-resize";

export const BUBBLE_KEY = "storykeep-grok-bubble";
export const PANEL_KEY = "storykeep-grok-panel";

export const RESIZE_HANDLES: { edge: ResizeEdge; className: string; label: string }[] = [
  { edge: "n", className: "left-3 right-3 top-0 h-1.5 cursor-ns-resize", label: "Resize top" },
  { edge: "s", className: "left-3 right-3 bottom-0 h-1.5 cursor-ns-resize", label: "Resize bottom" },
  { edge: "e", className: "top-3 bottom-3 right-0 w-1.5 cursor-ew-resize", label: "Resize right" },
  { edge: "w", className: "top-3 bottom-3 left-0 w-1.5 cursor-ew-resize", label: "Resize left" },
  { edge: "ne", className: "right-0 top-0 size-3 cursor-nesw-resize", label: "Resize top right" },
  { edge: "nw", className: "left-0 top-0 size-3 cursor-nwse-resize", label: "Resize top left" },
  { edge: "se", className: "right-0 bottom-0 size-4 cursor-nwse-resize", label: "Resize bottom right" },
  { edge: "sw", className: "left-0 bottom-0 size-3 cursor-nesw-resize", label: "Resize bottom left" },
];

function loadPoint(key: string, fallback: { x: number; y: number }) {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as { x?: number; y?: number };
    if (typeof parsed.x === "number" && typeof parsed.y === "number") return { x: parsed.x, y: parsed.y };
  } catch {
    /* ignore */
  }
  return fallback;
}

function loadSize(vw: number, vh: number) {
  const fallback = defaultPanelSize(vw, vh);
  try {
    const raw = window.localStorage.getItem(PANEL_KEY);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as { w?: number; h?: number };
    if (typeof parsed.w === "number" && typeof parsed.h === "number") {
      const box = clampPanelBox(
        { left: PANEL_MARGIN, top: PANEL_MARGIN, w: parsed.w, h: parsed.h },
        vw,
        vh,
      );
      return { w: box.w, h: box.h };
    }
  } catch {
    /* ignore */
  }
  return fallback;
}

export function usePanelDragResize(mounted: boolean, fullscreen: boolean, open: boolean) {
  const [pos, setPos] = useState({ x: 24, y: 24 });
  const [size, setSize] = useState({ w: 640, h: 720 });
  const dragRef = useRef<{ kind: "bubble" | "panel"; dx: number; dy: number } | null>(null);
  const movedRef = useRef(false);
  const resizeRef = useRef<{
    edge: ResizeEdge;
    startX: number;
    startY: number;
    box: PanelBox;
  } | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!mounted) return;
    window.localStorage.setItem(BUBBLE_KEY, JSON.stringify(pos));
  }, [mounted, pos]);

  useEffect(() => {
    if (!mounted) return;
    const fallback = {
      x: Math.max(16, window.innerWidth - 72),
      y: Math.max(16, window.innerHeight - 72),
    };
    setPos(loadPoint(BUBBLE_KEY, fallback));
    setSize(loadSize(window.innerWidth, window.innerHeight));
  }, [mounted]);

  useEffect(() => {
    function onWindowResize() {
      if (!open || fullscreen) return;
      const next = clampPanelBox(
        { left: pos.x, top: pos.y, w: size.w, h: size.h },
        window.innerWidth,
        window.innerHeight,
      );
      setPos({ x: next.left, y: next.top });
      setSize({ w: next.w, h: next.h });
    }
    window.addEventListener("resize", onWindowResize);
    return () => window.removeEventListener("resize", onWindowResize);
  }, [fullscreen, open, pos.x, pos.y, size.h, size.w]);

  const onPointerMove = useCallback(
    (event: PointerEvent) => {
      if (fullscreen) return;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      if (resizeRef.current) {
        event.preventDefault();
        const session = resizeRef.current;
        const next = applyPanelResize(
          session.box,
          session.edge,
          event.clientX - session.startX,
          event.clientY - session.startY,
          vw,
          vh,
        );
        setPos({ x: next.left, y: next.top });
        setSize({ w: next.w, h: next.h });
        return;
      }
      const drag = dragRef.current;
      if (!drag) return;
      if (drag.kind === "panel") {
        const next = clampPanelBox(
          { left: event.clientX - drag.dx, top: event.clientY - drag.dy, w: size.w, h: size.h },
          vw,
          vh,
        );
        if (Math.abs(next.left - pos.x) > 3 || Math.abs(next.top - pos.y) > 3) movedRef.current = true;
        setPos({ x: next.left, y: next.top });
        return;
      }
      const x = Math.min(vw - 48, Math.max(8, event.clientX - drag.dx));
      const y = Math.min(vh - 48, Math.max(8, event.clientY - drag.dy));
      if (Math.abs(x - pos.x) > 3 || Math.abs(y - pos.y) > 3) movedRef.current = true;
      setPos({ x, y });
    },
    [fullscreen, pos.x, pos.y, size.h, size.w],
  );

  const onPointerUp = useCallback(() => {
    dragRef.current = null;
    resizeRef.current = null;
    document.body.style.removeProperty("user-select");
    document.body.style.removeProperty("cursor");
  }, []);

  useEffect(() => {
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerUp);
    };
  }, [onPointerMove, onPointerUp]);

  const startBubbleDrag = useCallback(
    (event: React.PointerEvent) => {
      movedRef.current = false;
      dragRef.current = { kind: "bubble", dx: event.clientX - pos.x, dy: event.clientY - pos.y };
    },
    [pos.x, pos.y],
  );

  const startPanelDrag = useCallback(
    (event: React.PointerEvent, panelBox: PanelBox) => {
      if (fullscreen) return;
      if ((event.target as HTMLElement).closest("button, [data-resize]")) return;
      dragRef.current = {
        kind: "panel",
        dx: event.clientX - panelBox.left,
        dy: event.clientY - panelBox.top,
      };
    },
    [fullscreen],
  );

  const startResize = useCallback(
    (event: React.PointerEvent, edge: ResizeEdge, box: PanelBox) => {
      event.preventDefault();
      event.stopPropagation();
      event.currentTarget.setPointerCapture(event.pointerId);
      document.body.style.userSelect = "none";
      resizeRef.current = {
        edge,
        startX: event.clientX,
        startY: event.clientY,
        box,
      };
    },
    [],
  );

  return {
    pos,
    setPos,
    size,
    setSize,
    dragRef,
    movedRef,
    resizeRef,
    panelRef,
    startBubbleDrag,
    startPanelDrag,
    startResize,
  };
}
