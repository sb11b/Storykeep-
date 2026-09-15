"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { GripVertical, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  ADD_NOTES_POS_KEY,
  canStartWindowDrag,
  clampWindowPoint,
  defaultAddNotesPos,
  defaultCenteredPos,
  parseStoredPoint,
  type WindowPoint,
} from "@/lib/movable-window";
import { cn } from "@/lib/utils";

function readSaved(key: string): WindowPoint | null {
  try {
    return parseStoredPoint(window.localStorage.getItem(key));
  } catch {
    return null;
  }
}

function writeSaved(key: string, point: WindowPoint) {
  try {
    window.localStorage.setItem(key, JSON.stringify(point));
  } catch {
    /* ignore quota */
  }
}

export function useMovableWindow({
  storageKey,
  open,
  defaultMode = "left",
  estimatedSize = { w: 320, h: 280 },
}: {
  storageKey: string;
  open: boolean;
  defaultMode?: "left" | "center";
  estimatedSize?: { w: number; h: number };
}) {
  const [pos, setPos] = useState<WindowPoint>({ x: 16, y: 16 });
  const posRef = useRef(pos);
  posRef.current = pos;
  const dragRef = useRef<{ dx: number; dy: number; w: number; h: number } | null>(null);

  const place = useCallback(
    (boxW: number, boxH: number, preferred?: WindowPoint | null) => {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const saved = preferred ?? readSaved(storageKey);
      const fallback =
        defaultMode === "center"
          ? defaultCenteredPos(vw, vh, boxW, boxH)
          : defaultAddNotesPos(vw, vh, boxW, boxH);
      const next = clampWindowPoint(saved?.x ?? fallback.x, saved?.y ?? fallback.y, boxW, boxH, vw, vh);
      setPos(next);
      return next;
    },
    [defaultMode, storageKey],
  );

  useLayoutEffect(() => {
    if (!open) return;
    place(estimatedSize.w, estimatedSize.h);
  }, [open, estimatedSize.h, estimatedSize.w, place]);

  useEffect(() => {
    if (!open) return;
    const onResize = () => {
      place(estimatedSize.w, estimatedSize.h, posRef.current);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [open, estimatedSize.h, estimatedSize.w, place]);

  const onHandlePointerDown = useCallback(
    (event: PointerEvent<HTMLElement>) => {
      if (!canStartWindowDrag(event.target)) return;
      const box =
        (event.currentTarget.closest("[data-movable-window]") as HTMLElement | null) ?? event.currentTarget;
      const rect = box.getBoundingClientRect();
      dragRef.current = {
        dx: event.clientX - rect.left,
        dy: event.clientY - rect.top,
        w: rect.width,
        h: rect.height,
      };
      event.preventDefault();
      try {
        event.currentTarget.setPointerCapture(event.pointerId);
      } catch {
        /* capture is optional */
      }
    },
    [],
  );

  useEffect(() => {
    if (!open) return;
    const onMove = (event: globalThis.PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const next = clampWindowPoint(
        event.clientX - drag.dx,
        event.clientY - drag.dy,
        drag.w,
        drag.h,
        window.innerWidth,
        window.innerHeight,
      );
      setPos(next);
      writeSaved(storageKey, next);
    };
    const onUp = () => {
      dragRef.current = null;
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [open, storageKey]);

  return { pos, onHandlePointerDown, place };
}

export function MovableWindow({
  open,
  onClose,
  title,
  children,
  className,
  width = 320,
  storageKey = ADD_NOTES_POS_KEY,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  className?: string;
  width?: number;
  storageKey?: string;
}) {
  const { pos, onHandlePointerDown } = useMovableWindow({
    storageKey,
    open,
    defaultMode: "left",
    estimatedSize: { w: width, h: 280 },
  });
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!mounted || !open) return null;

  return createPortal(
    <div
      data-movable-window
      role="dialog"
      aria-label={title}
      className={cn(
        "fixed z-[100] flex max-h-[min(90vh,28rem)] w-[min(92vw,22rem)] flex-col rounded-lg border bg-background shadow-lg",
        className,
      )}
      style={{ left: pos.x, top: pos.y, width }}
    >
      <div
        data-drag-handle
        className="flex shrink-0 cursor-grab items-center gap-1.5 border-b px-2 py-1.5 active:cursor-grabbing"
        onPointerDown={onHandlePointerDown}
      >
        <GripVertical className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
        <span className="min-w-0 flex-1 truncate text-sm font-medium">{title}</span>
        <Button type="button" size="icon-sm" variant="ghost" data-no-drag aria-label="Close" onClick={onClose}>
          <X className="size-3.5" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-2">{children}</div>
    </div>,
    document.body,
  );
}
