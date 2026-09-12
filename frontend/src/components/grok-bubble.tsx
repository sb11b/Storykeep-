"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { Maximize2, Plus, Sparkles, X } from "lucide-react";
import { createGrokPane, GrokPane, type GrokPaneState } from "@/components/grok-pane";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const BUBBLE_KEY = "storykeep-grok-bubble";
const PANEL_KEY = "storykeep-grok-panel";
const DEFAULT_PANEL = { w: 380, h: 520 };
const MAX_PANES = 4;

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

function loadSize() {
  try {
    const raw = window.localStorage.getItem(PANEL_KEY);
    if (!raw) return DEFAULT_PANEL;
    const parsed = JSON.parse(raw) as { w?: number; h?: number };
    if (typeof parsed.w === "number" && typeof parsed.h === "number") {
      return { w: Math.max(300, parsed.w), h: Math.max(320, parsed.h) };
    }
  } catch {
    /* ignore */
  }
  return DEFAULT_PANEL;
}

function paneGridStyle(count: number): CSSProperties {
  if (count <= 1) return { gridTemplateColumns: "1fr", gridTemplateRows: "1fr" };
  if (count === 2) return { gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr" };
  return { gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr 1fr" };
}

function paneCellStyle(count: number, index: number): CSSProperties | undefined {
  if (count === 3 && index === 2) return { gridColumn: "1 / span 2" };
  return undefined;
}

export function GrokBubble({
  articleId,
  articleTitle,
  articleGuid,
  sourceRef,
  articleBody,
  onSavedNote,
  onStopArticleListen,
}: {
  articleId: string | null;
  articleTitle: string | null;
  articleGuid?: string | null;
  sourceRef?: string | null;
  articleBody?: string | null;
  onSavedNote: (noteId?: string, destination?: "notes" | "schoolwork") => Promise<void>;
  onStopArticleListen?: () => void;
}) {
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [pos, setPos] = useState({ x: 24, y: 24 });
  const [size, setSize] = useState(DEFAULT_PANEL);
  const [panes, setPanes] = useState<GrokPaneState[]>(() => [createGrokPane()]);
  const [focusedPaneId, setFocusedPaneId] = useState<string>(() => panes[0]!.id);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const [locked, setLocked] = useState(false);
  const [listening, setListening] = useState(false);
  const activeListenStopRef = useRef<(() => void) | null>(null);
  const dragRef = useRef<{ kind: "bubble" | "panel"; dx: number; dy: number } | null>(null);
  const movedRef = useRef(false);
  const resizeRef = useRef<{ x: number; y: number; w: number; h: number } | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const focusedPane = panes.find((pane) => pane.id === focusedPaneId) ?? panes[0]!;

  useEffect(() => {
    setMounted(true);
    const fallback = {
      x: Math.max(16, window.innerWidth - 72),
      y: Math.max(16, window.innerHeight - 72),
    };
    setPos(loadPoint(BUBBLE_KEY, fallback));
    setSize(loadSize());
    api
      .chatStatus()
      .then((row) => {
        setEnabled(row.enabled);
        setLocked(Boolean(row.locked));
      })
      .catch(() => {
        setEnabled(false);
        setLocked(false);
      });
    api
      .tts()
      .then((row) => setTtsEnabled(row.enabled))
      .catch(() => setTtsEnabled(false));
  }, []);

  useEffect(() => {
    if (!mounted) return;
    window.localStorage.setItem(BUBBLE_KEY, JSON.stringify(pos));
  }, [mounted, pos]);

  useEffect(() => {
    if (!mounted) return;
    window.localStorage.setItem(PANEL_KEY, JSON.stringify(size));
  }, [mounted, size]);

  useEffect(() => {
    if (!panes.some((pane) => pane.id === focusedPaneId)) {
      setFocusedPaneId(panes[0]?.id ?? focusedPaneId);
    }
  }, [focusedPaneId, panes]);

  const exitFullscreen = useCallback(() => {
    setPanes((current) => {
      const keep = current.find((pane) => pane.id === focusedPaneId) ?? current[0];
      return keep ? [keep] : [createGrokPane()];
    });
    setFullscreen(false);
  }, [focusedPaneId]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (!open) return;
      const target = event.target as HTMLElement | null;
      const inPanel = Boolean(panelRef.current && target && panelRef.current.contains(target));
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (listening && activeListenStopRef.current) {
          activeListenStopRef.current();
          return;
        }
        if (fullscreen) {
          exitFullscreen();
          return;
        }
        setOpen(false);
        return;
      }
      if (event.key === "f" && !event.metaKey && !event.ctrlKey && !event.altKey && inPanel) {
        if (target?.closest("textarea, input, select, [contenteditable='true']")) return;
        event.preventDefault();
        setFullscreen((current) => !current);
      }
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [exitFullscreen, fullscreen, listening, open]);

  function handleActivateListen(stop: (() => void) | null) {
    activeListenStopRef.current = stop;
    setListening(Boolean(stop));
  }

  function closePanel() {
    exitFullscreen();
    setOpen(false);
  }

  function toggleFullscreen() {
    if (fullscreen) {
      exitFullscreen();
      return;
    }
    setFullscreen(true);
  }

  function addPane() {
    if (locked || panes.length >= MAX_PANES) return;
    const next = createGrokPane();
    setPanes((current) => [...current, next]);
    setFocusedPaneId(next.id);
  }

  function removePane(id: string) {
    setPanes((current) => {
      const next = current.filter((pane) => pane.id !== id);
      const result = next.length ? next : [createGrokPane()];
      setFocusedPaneId((focused) => (focused === id ? result[0]!.id : focused));
      return result;
    });
  }

  function updatePane(id: string, updater: (pane: GrokPaneState) => GrokPaneState) {
    setPanes((current) => current.map((pane) => (pane.id === id ? updater(pane) : pane)));
  }

  const onPointerMove = useCallback(
    (event: PointerEvent) => {
      if (fullscreen) return;
      if (resizeRef.current) {
        const nextW = Math.min(window.innerWidth - 24, Math.max(300, resizeRef.current.w + (event.clientX - resizeRef.current.x)));
        const nextH = Math.min(window.innerHeight - 24, Math.max(320, resizeRef.current.h + (event.clientY - resizeRef.current.y)));
        setSize({ w: nextW, h: nextH });
        return;
      }
      const drag = dragRef.current;
      if (!drag) return;
      const x = Math.min(window.innerWidth - 48, Math.max(8, event.clientX - drag.dx));
      const y = Math.min(window.innerHeight - 48, Math.max(8, event.clientY - drag.dy));
      if (Math.abs(x - pos.x) > 3 || Math.abs(y - pos.y) > 3) movedRef.current = true;
      setPos({ x, y });
    },
    [fullscreen, pos.x, pos.y],
  );

  const onPointerUp = useCallback(() => {
    dragRef.current = null;
    resizeRef.current = null;
  }, []);

  useEffect(() => {
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [onPointerMove, onPointerUp]);

  if (!mounted) return null;

  const bubble = (
    <button
      type="button"
      className="fixed z-[80] flex size-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg ring-1 ring-black/10"
      style={{ left: pos.x, top: pos.y }}
      aria-label="Open Grok chat"
      onPointerDown={(event) => {
        movedRef.current = false;
        dragRef.current = { kind: "bubble", dx: event.clientX - pos.x, dy: event.clientY - pos.y };
      }}
      onClick={() => {
        if (movedRef.current) return;
        setOpen(true);
      }}
    >
      <Sparkles className="size-5" />
    </button>
  );

  const panelLeft = Math.min(pos.x, window.innerWidth - size.w - 8);
  const panelTop = Math.min(pos.y, window.innerHeight - size.h - 8);
  const subtitle =
    focusedPane.includeArticle && articleTitle
      ? `Connected: ${articleTitle}`
      : articleTitle
        ? "Thread only (article not included)"
        : "School coding help";

  const panel = (
    <div
      ref={panelRef}
      className={cn(
        "fixed flex flex-col overflow-hidden border bg-popover text-popover-foreground shadow-xl",
        fullscreen ? "inset-0 z-[90] h-[100dvh] w-[100vw] rounded-none" : "z-[80] rounded-xl",
      )}
      style={
        fullscreen
          ? undefined
          : {
              left: panelLeft,
              top: panelTop,
              width: size.w,
              height: size.h,
            }
      }
    >
      <div
        className={cn(
          "flex shrink-0 items-center gap-2 border-b px-3 py-2",
          fullscreen ? "cursor-default" : "cursor-grab active:cursor-grabbing",
        )}
        onPointerDown={(event) => {
          if (fullscreen) return;
          if ((event.target as HTMLElement).closest("button")) return;
          dragRef.current = { kind: "panel", dx: event.clientX - pos.x, dy: event.clientY - pos.y };
        }}
      >
        <Sparkles className="size-4 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium leading-none">Grok</p>
          <p className="truncate text-[11px] text-muted-foreground">{fullscreen ? `${panes.length} pane${panes.length === 1 ? "" : "s"}` : subtitle}</p>
        </div>
        {fullscreen && !locked && panes.length < MAX_PANES ? (
          <Button size="sm" variant="outline" className="h-7 gap-1 px-2 text-xs" onClick={addPane}>
            <Plus className="size-3.5" />
            Add Grok
          </Button>
        ) : null}
        {fullscreen ? (
          <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={exitFullscreen}>
            Exit full screen
          </Button>
        ) : (
          <Button size="icon-xs" variant="ghost" onClick={toggleFullscreen} aria-label="Full screen" title="Full screen (f)">
            <Maximize2 className="size-3.5" />
          </Button>
        )}
        <Button size="icon-xs" variant="ghost" onClick={closePanel} aria-label="Close chat">
          <X className="size-3.5" />
        </Button>
      </div>

      {fullscreen ? (
        <div className="grid min-h-0 flex-1 gap-px bg-border" style={paneGridStyle(panes.length)}>
          {panes.map((pane, index) => (
            <div
              key={pane.id}
              className="min-h-0 overflow-hidden bg-popover"
              style={paneCellStyle(panes.length, index)}
            >
              <GrokPane
                pane={pane}
                label={`Grok ${index + 1}`}
                compact
                focused={pane.id === focusedPaneId}
                canRemove={panes.length > 1}
                articleId={articleId}
                articleTitle={articleTitle}
                articleGuid={articleGuid}
                sourceRef={sourceRef}
                articleBody={articleBody}
                enabled={Boolean(enabled)}
                ttsEnabled={ttsEnabled}
                locked={locked}
                onFocus={() => setFocusedPaneId(pane.id)}
                onUpdate={(updater) => updatePane(pane.id, updater)}
                onRemove={() => removePane(pane.id)}
                onSavedNote={onSavedNote}
                onActivateListen={handleActivateListen}
                onStopArticleListen={onStopArticleListen}
              />
            </div>
          ))}
        </div>
      ) : (
        <GrokPane
          pane={focusedPane}
          label="Grok"
          articleId={articleId}
          articleTitle={articleTitle}
          articleGuid={articleGuid}
          sourceRef={sourceRef}
          articleBody={articleBody}
          enabled={Boolean(enabled)}
          ttsEnabled={ttsEnabled}
          locked={locked}
          onFocus={() => setFocusedPaneId(focusedPane.id)}
          onUpdate={(updater) => updatePane(focusedPane.id, updater)}
          onSavedNote={onSavedNote}
          onActivateListen={handleActivateListen}
          onStopArticleListen={onStopArticleListen}
        />
      )}

      {!fullscreen ? (
        <button
          type="button"
          className="absolute bottom-1 right-1 size-4 cursor-se-resize"
          aria-label="Resize chat"
          onPointerDown={(event) => {
            event.preventDefault();
            resizeRef.current = { x: event.clientX, y: event.clientY, w: size.w, h: size.h };
          }}
        >
          <Maximize2 className="size-3 text-muted-foreground" />
        </button>
      ) : null}
    </div>
  );

  return createPortal(
    <>
      {!open ? bubble : null}
      {open ? panel : null}
    </>,
    document.body,
  );
}
