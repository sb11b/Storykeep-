"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { LoaderCircle, Maximize2, MessageSquarePlus, MoreHorizontal, Pencil, Plus, Sparkles, Trash2, X } from "lucide-react";
import { createGrokPane, GrokPane, type GrokPaneState } from "@/components/grok-pane";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { useDictation } from "@/components/dictation";
import { api } from "@/lib/api";
import { grokModelLabel } from "@/lib/grok-model";
import type { GrokConversation, TtsVoice } from "@/lib/types";
import type { NoteDestination } from "@/lib/destinations";
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
  onSavedNote: (noteId?: string, destination?: NoteDestination, folderId?: string | null) => Promise<void>;
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
  const [ttsVoices, setTtsVoices] = useState<TtsVoice[]>([]);
  const [sttEnabled, setSttEnabled] = useState(false);
  const [locked, setLocked] = useState(false);
  const dictation = useDictation();
  const [persist, setPersist] = useState(false);
  const [chatModels, setChatModels] = useState<string[]>(["grok-4", "grok-4-fast"]);
  const [conversations, setConversations] = useState<GrokConversation[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const renameInputRef = useRef<HTMLInputElement>(null);
  const [listening, setListening] = useState(false);
  const activeListenStopRef = useRef<(() => void) | null>(null);
  const dragRef = useRef<{ kind: "bubble" | "panel"; dx: number; dy: number } | null>(null);
  const movedRef = useRef(false);
  const resizeRef = useRef<{ x: number; y: number; w: number; h: number } | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const focusedPane = panes.find((pane) => pane.id === focusedPaneId) ?? panes[0]!;

  const refreshHistory = useCallback(async () => {
    if (!persist) return;
    setHistoryLoading(true);
    try {
      setConversations(await api.chatConversations());
    } catch {
      /* ignore */
    } finally {
      setHistoryLoading(false);
    }
  }, [persist]);

  useEffect(() => {
    if (open && persist) void refreshHistory();
  }, [open, persist, refreshHistory]);

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
        setPersist(Boolean(row.persist ?? !row.locked));
        if (row.models?.length) setChatModels(row.models);
      })
      .catch(() => {
        setEnabled(false);
        setLocked(false);
        setPersist(false);
      });
    api
      .tts()
      .then((row) => {
        setTtsEnabled(row.enabled);
        setTtsVoices(row.voices ?? []);
      })
      .catch(() => {
        setTtsEnabled(false);
        setTtsVoices([]);
      });
    api
      .stt()
      .then((row) => setSttEnabled(row.enabled))
      .catch(() => setSttEnabled(false));
  }, []);

  useEffect(() => {
    if (!open) dictation?.stop();
  }, [open, dictation]);

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
        if (dictation?.listening) {
          dictation.stop();
          return;
        }
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
  }, [dictation, exitFullscreen, fullscreen, listening, open]);

  function handleActivateListen(stop: (() => void) | null) {
    activeListenStopRef.current = stop;
    setListening(Boolean(stop));
  }

  function closePanel() {
    dictation?.stop();
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

  function startNewChat() {
    updatePane(focusedPaneId, (pane) => ({
      ...pane,
      conversationId: null,
      messages: [],
      recapQuestion: false,
    }));
  }

  async function loadConversation(conversationId: string) {
    try {
      const detail = await api.chatConversation(conversationId);
      updatePane(focusedPaneId, (pane) => ({
        ...pane,
        conversationId: detail.id,
        modelChoice: detail.model || "auto",
        lastResolvedModel: detail.last_model ?? null,
        messages: detail.messages.map((item) => ({
          id: item.id,
          role: item.role,
          content: item.content,
        })),
        draft: "",
        recapQuestion: Boolean(detail.recap_question),
      }));
    } catch {
      /* ignore */
    }
  }

  async function deleteConversation(conversationId: string) {
    try {
      await api.deleteChatConversation(conversationId);
      setConversations((current) => current.filter((row) => row.id !== conversationId));
      const active = panes.find((pane) => pane.conversationId === conversationId);
      if (active) {
        updatePane(active.id, (pane) => ({ ...pane, conversationId: null, messages: [] }));
      }
      if (renamingId === conversationId) {
        setRenamingId(null);
        setRenameDraft("");
      }
    } catch {
      /* ignore */
    }
  }

  function startRename(row: GrokConversation) {
    setRenamingId(row.id);
    setRenameDraft(row.title);
    window.requestAnimationFrame(() => renameInputRef.current?.select());
  }

  function cancelRename() {
    setRenamingId(null);
    setRenameDraft("");
  }

  async function commitRename(conversationId: string) {
    if (!persist) return;
    const draft = renameDraft;
    setRenamingId(null);
    setRenameDraft("");
    try {
      const updated = await api.patchChatConversation(conversationId, { title: draft });
      setConversations((current) =>
        current.map((row) => (row.id === conversationId ? { ...row, title: updated.title } : row)),
      );
    } catch {
      /* ignore */
    }
  }

  const historySidebar = persist ? (
    <aside className="flex w-44 shrink-0 flex-col overflow-hidden border-r bg-muted/15">
      <div className="shrink-0 border-b p-2">
        <Button size="sm" variant="secondary" className="h-7 w-full gap-1 text-xs" onClick={startNewChat}>
          <MessageSquarePlus className="size-3.5" />
          New chat
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-1">
        {historyLoading ? (
          <p className="flex items-center gap-1 px-2 py-2 text-[11px] text-muted-foreground">
            <LoaderCircle className="size-3 animate-spin" />
            Loading…
          </p>
        ) : conversations.length === 0 ? (
          <p className="px-2 py-2 text-[11px] text-muted-foreground">Past chats appear here.</p>
        ) : (
          conversations.map((row) => {
            const active = focusedPane.conversationId === row.id;
            const renaming = renamingId === row.id;
            return (
              <div key={row.id} className="group flex items-start gap-0.5">
                {renaming ? (
                  <Input
                    ref={renameInputRef}
                    value={renameDraft}
                    className="h-7 min-w-0 flex-1 px-2 text-[11px]"
                    aria-label="Rename chat"
                    onChange={(event) => setRenameDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        void commitRename(row.id);
                      }
                      if (event.key === "Escape") {
                        event.preventDefault();
                        cancelRename();
                      }
                    }}
                    onBlur={() => void commitRename(row.id)}
                  />
                ) : (
                  <button
                    type="button"
                    className={cn(
                      "min-w-0 flex-1 rounded-md px-2 py-1.5 text-left text-[11px] leading-snug hover:bg-accent/60",
                      active && "bg-accent/80 font-medium",
                    )}
                    title={row.title}
                    onClick={() => void loadConversation(row.id)}
                    onDoubleClick={(event) => {
                      event.preventDefault();
                      startRename(row);
                    }}
                  >
                    <span className="line-clamp-2">{row.title}</span>
                    <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">
                      {grokModelLabel(row.model || "auto", row.last_model)}
                    </span>
                  </button>
                )}
                {!renaming ? (
                  <DropdownMenu>
                    <DropdownMenuTrigger
                      render={
                        <Button
                          size="icon-xs"
                          variant="ghost"
                          className="mt-0.5 shrink-0 opacity-0 group-hover:opacity-100 data-popup-open:opacity-100"
                          aria-label={`Options for ${row.title}`}
                        >
                          <MoreHorizontal className="size-3 text-muted-foreground" />
                        </Button>
                      }
                    />
                    <DropdownMenuContent align="start" className="min-w-36">
                      <DropdownMenuItem onClick={() => startRename(row)}>
                        <Pencil className="size-3.5" />
                        Rename
                      </DropdownMenuItem>
                      <DropdownMenuItem variant="destructive" onClick={() => void deleteConversation(row.id)}>
                        <Trash2 className="size-3.5" />
                        Delete
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </aside>
  ) : null;

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

      <div className="flex min-h-0 flex-1 overflow-hidden">
        {historySidebar}
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
                  sttEnabled={sttEnabled}
                  locked={locked}
                  onFocus={() => setFocusedPaneId(pane.id)}
                  onUpdate={(updater) => updatePane(pane.id, updater)}
                  onRemove={() => removePane(pane.id)}
                  onSavedNote={onSavedNote}
                  onActivateListen={handleActivateListen}
                  onStopArticleListen={onStopArticleListen}
                  onHistoryChanged={() => void refreshHistory()}
                  chatModels={chatModels}
                  persist={persist}
                  panelOpen={open}
                  ttsVoices={ttsVoices}
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
            sttEnabled={sttEnabled}
            locked={locked}
            onFocus={() => setFocusedPaneId(focusedPane.id)}
            onUpdate={(updater) => updatePane(focusedPane.id, updater)}
            onSavedNote={onSavedNote}
            onActivateListen={handleActivateListen}
            onStopArticleListen={onStopArticleListen}
            onHistoryChanged={() => void refreshHistory()}
            chatModels={chatModels}
            persist={persist}
            panelOpen={open}
            ttsVoices={ttsVoices}
          />
        )}
      </div>

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
