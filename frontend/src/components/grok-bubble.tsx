"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { CalendarClock, ChevronLeft, ChevronRight, History, LoaderCircle, Maximize2, MessageSquarePlus, Pencil, Plus, Sparkles, Trash2, X } from "lucide-react";
import { createGrokPane, defaultGrokPaneName, GrokPane, type GrokPaneState } from "@/components/grok-pane";
import { GrokRowMenu } from "@/components/grok-row-menu";
import { JuniorJobsPanel } from "@/components/junior-jobs-panel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useDictation } from "@/components/dictation";
import { api } from "@/lib/api";
import { toastActionError } from "@/lib/toast-message";
import { grokModelLabel, isGrokReasoningEffort, spendChipLabel } from "@/lib/grok-model";
import type { GrokConversation, TtsVoice } from "@/lib/types";
import { parseCustomNoteShelves, uniqueShelfId, type CustomNoteShelf, type FilingDestination } from "@/lib/custom-note-shelves";
import {
  labelsFromPanes,
  loadSavedGrokPanes,
  mergePreferenceLabels,
  saveGrokPanes,
  scrubDefaultPaneLabels,
} from "@/lib/grok-pane-storage";
import {
  PANEL_MARGIN,
  applyPanelResize,
  clampPanelBox,
  defaultPanelSize,
  type PanelBox,
  type ResizeEdge,
} from "@/lib/grok-panel-resize";
import { cn } from "@/lib/utils";
import { loadJuniorRailHidden, saveJuniorRailHidden } from "@/lib/junior-rail";

const BUBBLE_KEY = "storykeep-grok-bubble";
const PANEL_KEY = "storykeep-grok-panel";
const MAX_PANES = 4;

const RESIZE_HANDLES: { edge: ResizeEdge; className: string; label: string }[] = [
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
  onSavedNote: (noteId?: string, destination?: FilingDestination, folderId?: string | null) => Promise<void>;
  onStopArticleListen?: () => void;
}) {
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [pos, setPos] = useState({ x: 24, y: 24 });
  const [size, setSize] = useState({ w: 640, h: 720 });
  const [panes, setPanes] = useState<GrokPaneState[]>(() => loadSavedGrokPanes() ?? [createGrokPane(0)]);
  const [focusedPaneId, setFocusedPaneId] = useState<string>(() => (loadSavedGrokPanes() ?? [createGrokPane(0)])[0]!.id);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const [ttsVoices, setTtsVoices] = useState<TtsVoice[]>([]);
  const [sttEnabled, setSttEnabled] = useState(false);
  const [locked, setLocked] = useState(false);
  const dictation = useDictation();
  const [persist, setPersist] = useState(false);
  const [chatModels, setChatModels] = useState<string[]>(["grok-4.6", "grok-4.3"]);
  const [conversations, setConversations] = useState<GrokConversation[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const renameInputRef = useRef<HTMLInputElement>(null);
  const [renamingPaneId, setRenamingPaneId] = useState<string | null>(null);
  const [paneRenameDraft, setPaneRenameDraft] = useState("");
  const paneRenameInputRef = useRef<HTMLInputElement>(null);
  const paneLabelsLoadedRef = useRef(false);
  const [customShelves, setCustomShelves] = useState<CustomNoteShelf[]>([]);
  const [listening, setListening] = useState(false);
  const [railHidden, setRailHidden] = useState(() => loadJuniorRailHidden());
  const historyListRef = useRef<HTMLDivElement>(null);
  const jobsRailRef = useRef<HTMLElement | null>(null);
  const activeListenStopRef = useRef<(() => void) | null>(null);
  const dragRef = useRef<{ kind: "bubble" | "panel"; dx: number; dy: number } | null>(null);
  const movedRef = useRef(false);
  const resizeRef = useRef<{
    edge: ResizeEdge;
    startX: number;
    startY: number;
    box: PanelBox;
  } | null>(null);
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
    if (!persist) return;
    for (const pane of panes) {
      const id = pane.conversationId;
      if (!id || pane.messages.length || restoredConversationsRef.current.has(id)) continue;
      restoredConversationsRef.current.add(id);
      void loadConversationInto(pane.id, id);
    }
  }, [loadConversationInto, panes, persist]);

  useEffect(() => {
    if (paneLabelsLoadedRef.current) return;
    paneLabelsLoadedRef.current = true;
    void api
      .getPreferences()
      .then((prefs) => {
        setCustomShelves(parseCustomNoteShelves(prefs));
        const labels = prefs.grok_pane_labels as Record<string, string> | undefined;
        if (!labels || !Object.keys(labels).length) return;
        setPanes((current) => {
          const merged = mergePreferenceLabels(current, labels);
          saveGrokPanes(merged);
          return merged;
        });
      })
      .catch(() => {
        /* ignore */
      });
  }, []);

  async function createNoteShelf() {
    const name = window.prompt("New shelf name:")?.trim();
    if (!name) return;
    const id = uniqueShelfId(name, customShelves);
    const next = [...customShelves, { id, name }];
    try {
      const prefs = await api.updatePreferences({ custom_note_shelves: next });
      setCustomShelves(parseCustomNoteShelves(prefs));
      updatePane(focusedPaneId, (pane) => ({ ...pane, noteDest: id, noteFolderId: null }));
    } catch {
      /* ignore */
    }
  }

  useEffect(() => {
    if (!mounted) return;
    saveGrokPanes(panes);
  }, [mounted, panes]);

  useEffect(() => {
    setMounted(true);
    const fallback = {
      x: Math.max(16, window.innerWidth - 72),
      y: Math.max(16, window.innerHeight - 72),
    };
    setPos(loadPoint(BUBBLE_KEY, fallback));
    setSize(loadSize(window.innerWidth, window.innerHeight));
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
    Promise.all([
      api.tts().catch(() => ({ enabled: false, provider: "xai", voices: [] as TtsVoice[] })),
      api.ttsVoices().catch(() => ({ voices: [] as TtsVoice[] })),
    ]).then(([status, voicesPayload]) => {
      setTtsEnabled(status.enabled);
      const voices = voicesPayload.voices?.length ? voicesPayload.voices : status.voices ?? [];
      setTtsVoices(voices);
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
    saveJuniorRailHidden(railHidden);
  }, [mounted, railHidden]);

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

  useEffect(() => {
    if (!panes.some((pane) => pane.id === focusedPaneId)) {
      setFocusedPaneId(panes[0]?.id ?? focusedPaneId);
    }
  }, [focusedPaneId, panes]);

  const exitFullscreen = useCallback(() => {
    setPanes((current) => {
      const keep = current.find((pane) => pane.id === focusedPaneId) ?? current[0];
      return keep ? [keep] : [createGrokPane(0)];
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

  async function persistPaneLabels(nextPanes: GrokPaneState[]) {
    saveGrokPanes(nextPanes);
    try {
      const prefs = await api.getPreferences();
      const existing = scrubDefaultPaneLabels(prefs.grok_pane_labels as Record<string, string> | undefined);
      const merged = scrubDefaultPaneLabels({ ...existing, ...labelsFromPanes(nextPanes) });
      await api.updatePreferences({ grok_pane_labels: merged });
    } catch (error) {
      toastActionError(error, "save pane name", "Could not save that pane name");
    }
  }

  function addPane() {
    if (locked || panes.length >= MAX_PANES) return;
    const next = createGrokPane(panes.length);
    setPanes((current) => {
      const result = [...current, next];
      void persistPaneLabels(result);
      return result;
    });
    setFocusedPaneId(next.id);
  }

  function removePane(id: string) {
    setPanes((current) => {
      const next = current.filter((pane) => pane.id !== id);
      const result = next.length ? next : [createGrokPane(0)];
      setFocusedPaneId((focused) => (focused === id ? result[0]!.id : focused));
      return result;
    });
  }

  function updatePane(id: string, updater: (pane: GrokPaneState) => GrokPaneState) {
    setPanes((current) => current.map((pane) => (pane.id === id ? updater(pane) : pane)));
  }

  const restoredConversationsRef = useRef<Set<string>>(new Set());

  const loadConversationInto = useCallback(async (paneId: string, conversationId: string) => {
    try {
      const detail = await api.chatConversation(conversationId);
      setPanes((current) =>
        current.map((pane) =>
          pane.id !== paneId
            ? pane
            : {
                ...pane,
                conversationId: detail.id,
                modelChoice: detail.model || "auto",
                lastResolvedModel: detail.last_model ?? null,
                reasoningEffort: isGrokReasoningEffort(detail.reasoning) ? detail.reasoning : "low",
                lastResolvedReasoning: detail.last_reasoning ?? null,
                savedNoteId: detail.saved_note_id ?? null,
                conversationTitle: detail.title || null,
                messages: detail.messages.map((item) => ({
                  id: item.id,
                  role: item.role,
                  content: item.content,
                  files: item.files?.map((file) => ({
                    media_id: file.media_id,
                    filename: file.filename,
                    content_type: file.content_type,
                    kind: file.kind,
                    url: file.url,
                    byte_size: file.byte_size,
                    extract_text: file.extract_text,
                  })),
                  routeLabel:
                    item.role === "assistant" ? spendChipLabel(detail.last_model, detail.last_reasoning) : null,
                })),
                recapQuestion: Boolean(detail.recap_question),
              },
        ),
      );
    } catch {
      setPanes((current) =>
        current.map((pane) =>
          pane.id === paneId && pane.conversationId === conversationId ? { ...pane, conversationId: null } : pane,
        ),
      );
    }
  }, []);

  function startNewChat() {
    updatePane(focusedPaneId, (pane) => ({
      ...pane,
      conversationId: null,
      messages: [],
      recapQuestion: false,
      pendingAttachments: [],
      savedNoteId: null,
      conversationTitle: null,
    }));
  }

  async function loadConversation(conversationId: string) {
    restoredConversationsRef.current.add(conversationId);
    await loadConversationInto(focusedPaneId, conversationId);
    updatePane(focusedPaneId, (pane) => ({ ...pane, draft: "", pendingAttachments: [] }));
  }

  async function deleteConversation(row: GrokConversation) {
    if (!window.confirm(`Delete "${row.title}"? This cannot be undone.`)) return;
    try {
      await api.deleteChatConversation(row.id);
      setConversations((current) => current.filter((item) => item.id !== row.id));
      const clearedFocused = focusedPane.conversationId === row.id;
      setPanes((current) =>
        current.map((pane) =>
          pane.conversationId === row.id
            ? { ...pane, conversationId: null, messages: [], draft: "", recapQuestion: false, pendingAttachments: [], savedNoteId: null, conversationTitle: null }
            : pane,
        ),
      );
      if (clearedFocused) startNewChat();
      if (renamingId === row.id) {
        setRenamingId(null);
        setRenameDraft("");
      }
    } catch (error) {
      toastActionError(error, "delete chat", "Could not delete that chat");
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
      setPanes((current) =>
        current.map((pane) =>
          pane.conversationId === conversationId ? { ...pane, conversationTitle: updated.title } : pane,
        ),
      );
    } catch {
      /* ignore */
    }
  }

  function startPaneRename(paneId: string) {
    const pane = panes.find((item) => item.id === paneId);
    if (!pane) return;
    setRenamingPaneId(paneId);
    setPaneRenameDraft(pane.displayName);
    window.requestAnimationFrame(() => paneRenameInputRef.current?.select());
  }

  function cancelPaneRename() {
    setRenamingPaneId(null);
    setPaneRenameDraft("");
  }

  async function commitPaneRename(paneId: string) {
    const trimmed = paneRenameDraft.trim().slice(0, 120);
    setRenamingPaneId(null);
    setPaneRenameDraft("");
    if (!trimmed) return;
    let nextPanes: GrokPaneState[] = [];
    setPanes((current) => {
      nextPanes = current.map((pane) => (pane.id === paneId ? { ...pane, displayName: trimmed } : pane));
      return nextPanes;
    });
    await persistPaneLabels(nextPanes);
  }

  function paneRenameProps(paneId: string) {
    return {
      renamingLabel: renamingPaneId === paneId,
      renameDraft: paneRenameDraft,
      onStartRename: () => startPaneRename(paneId),
      onRenameDraftChange: setPaneRenameDraft,
      onCommitRename: () => void commitPaneRename(paneId),
      onCancelRename: cancelPaneRename,
    };
  }

  function showHistoryList() {
    setRailHidden(false);
    window.setTimeout(() => historyListRef.current?.scrollIntoView({ block: "nearest" }), 50);
  }

  function showJobsList() {
    setRailHidden(false);
    window.setTimeout(() => jobsRailRef.current?.scrollIntoView({ block: "nearest" }), 50);
  }

  const showJobsRail = Boolean(fullscreen && persist && !locked);

  const collapsedIconBtn =
    "h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground";

  const historySidebar = persist ? (
    railHidden ? (
      <aside className="flex w-11 shrink-0 flex-col items-center gap-1 border-r bg-muted/15 py-1">
        <Button
          type="button"
          size="icon-xs"
          variant="ghost"
          className={collapsedIconBtn}
          aria-label="Show panels"
          title="Show panels"
          onClick={() => setRailHidden(false)}
        >
          <ChevronRight className="size-3.5" />
        </Button>
        <Button
          type="button"
          size="icon-xs"
          variant="ghost"
          className={collapsedIconBtn}
          aria-label="New chat"
          title="New chat"
          onClick={startNewChat}
        >
          <MessageSquarePlus className="size-3.5" />
        </Button>
        <Button
          type="button"
          size="icon-xs"
          variant="ghost"
          className={collapsedIconBtn}
          aria-label="History"
          title="History"
          onClick={showHistoryList}
        >
          <History className="size-3.5" />
        </Button>
        {showJobsRail ? (
          <Button
            type="button"
            size="icon-xs"
            variant="ghost"
            className={collapsedIconBtn}
            aria-label="Jobs"
            title="Jobs"
            onClick={showJobsList}
          >
            <CalendarClock className="size-3.5" />
          </Button>
        ) : null}
      </aside>
    ) : (
    <aside className="flex w-44 shrink-0 flex-col overflow-hidden border-r bg-muted/15">
      <div className="flex shrink-0 items-center gap-1 border-b p-1.5">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 shrink-0 gap-0.5 px-1.5 text-[11px]"
          aria-label="Hide panels"
          title="Hide panels"
          onClick={() => setRailHidden(true)}
        >
          <ChevronLeft className="size-3.5" />
          Hide
        </Button>
        <Button size="sm" variant="secondary" className="h-7 min-w-0 flex-1 gap-1 px-1.5 text-xs" onClick={startNewChat}>
          <MessageSquarePlus className="size-3.5" />
          New chat
        </Button>
      </div>
      <div ref={historyListRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-1">
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
                      {grokModelLabel(row.model || "auto", row.last_model, row.last_reasoning)}
                    </span>
                  </button>
                )}
                {!renaming ? (
                  <GrokRowMenu
                    label={row.title}
                    className="mt-0.5"
                    items={[
                      {
                        key: "rename",
                        label: "Rename thread",
                        icon: <Pencil className="size-3.5" />,
                        onSelect: () => startRename(row),
                      },
                      {
                        key: "delete",
                        label: "Delete thread",
                        icon: <Trash2 className="size-3.5" />,
                        destructive: true,
                        onSelect: () => void deleteConversation(row),
                      },
                    ]}
                  />
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </aside>
    )
  ) : null;

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

  if (!mounted) return null;

  const bubbleLabel = focusedPane.displayName;

  const bubble = (
    <button
      type="button"
      className="fixed z-[80] flex size-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg ring-1 ring-black/10"
      style={{ left: pos.x, top: pos.y }}
      aria-label={`Open ${bubbleLabel} chat`}
      title={bubbleLabel}
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

  const panelBox = clampPanelBox(
    { left: pos.x, top: pos.y, w: size.w, h: size.h },
    window.innerWidth,
    window.innerHeight,
  );
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
              left: panelBox.left,
              top: panelBox.top,
              width: panelBox.w,
              height: panelBox.h,
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
          if ((event.target as HTMLElement).closest("button, [data-resize]")) return;
          dragRef.current = {
            kind: "panel",
            dx: event.clientX - panelBox.left,
            dy: event.clientY - panelBox.top,
          };
        }}
      >
        <Sparkles className="size-4 text-primary" />
        <div className="min-w-0 flex-1">
          {renamingPaneId === focusedPaneId ? (
            <Input
              ref={paneRenameInputRef}
              value={paneRenameDraft}
              className="h-7 max-w-[14rem] px-2 text-sm"
              aria-label="Rename pane"
              onChange={(event) => setPaneRenameDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void commitPaneRename(focusedPaneId);
                }
                if (event.key === "Escape") {
                  event.preventDefault();
                  cancelPaneRename();
                }
              }}
              onBlur={() => void commitPaneRename(focusedPaneId)}
            />
          ) : (
            <button
              type="button"
              className="truncate text-left text-sm font-medium leading-none hover:underline"
              title="Rename pane"
              onClick={() => startPaneRename(focusedPaneId)}
            >
              {focusedPane.displayName}
            </button>
          )}
          <p className="truncate text-[11px] text-muted-foreground">
            {fullscreen ? `${panes.length} pane${panes.length === 1 ? "" : "s"}` : subtitle}
          </p>
        </div>
        {renamingPaneId !== focusedPaneId ? (
          <GrokRowMenu
            label={focusedPane.displayName}
            items={[
              {
                key: "rename-pane",
                label: "Rename pane",
                icon: <Pencil className="size-3.5" />,
                onSelect: () => startPaneRename(focusedPaneId),
              },
            ]}
          />
        ) : null}
        {fullscreen && !locked && panes.length < MAX_PANES ? (
          <Button size="sm" variant="outline" className="h-7 gap-1 px-2 text-xs" onClick={addPane}>
            <Plus className="size-3.5" />
            Add pane
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
        {!railHidden && fullscreen && persist && !locked ? (
          <JuniorJobsPanel
            conversationId={focusedPane.conversationId}
            articleId={articleId}
            customShelves={customShelves}
            railRef={jobsRailRef}
            onRanConversation={(id) => {
              void loadConversation(id);
              void refreshHistory();
            }}
          />
        ) : null}
        {fullscreen ? (
          <div className="grid min-h-0 min-w-0 flex-1 gap-px overflow-hidden bg-border" style={paneGridStyle(panes.length)}>
            {panes.map((pane, index) => (
              <div
                key={pane.id}
                className="min-h-0 min-w-0 overflow-hidden bg-popover"
                style={paneCellStyle(panes.length, index)}
              >
                <GrokPane
                  pane={pane}
                  label={pane.displayName}
                  compact
                  focused={pane.id === focusedPaneId}
                  canRemove={panes.length > 1}
                  {...paneRenameProps(pane.id)}
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
                  customShelves={customShelves}
                  onCreateNoteShelf={createNoteShelf}
                />
              </div>
            ))}
          </div>
        ) : (
          <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <GrokPane
            key={focusedPane.id}
            pane={focusedPane}
            label={focusedPane.displayName}
            {...paneRenameProps(focusedPane.id)}
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
            customShelves={customShelves}
            onCreateNoteShelf={createNoteShelf}
          />
          </div>
        )}
      </div>

      {!fullscreen
        ? RESIZE_HANDLES.map((handle) => (
            <div
              key={handle.edge}
              data-resize={handle.edge}
              role="separator"
              aria-label={handle.label}
              aria-orientation={handle.edge === "e" || handle.edge === "w" ? "vertical" : "horizontal"}
              className={cn("absolute z-20 touch-none", handle.className)}
              onPointerDown={(event) => {
                event.preventDefault();
                event.stopPropagation();
                event.currentTarget.setPointerCapture(event.pointerId);
                document.body.style.userSelect = "none";
                resizeRef.current = {
                  edge: handle.edge,
                  startX: event.clientX,
                  startY: event.clientY,
                  box: panelBox,
                };
              }}
            >
              {handle.edge === "se" ? (
                <span className="pointer-events-none absolute bottom-0.5 right-0.5 block size-2.5 border-b-2 border-r-2 border-muted-foreground/80" />
              ) : null}
            </div>
          ))
        : null}
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
