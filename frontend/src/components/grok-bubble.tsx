"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { createPortal } from "react-dom";
import { Sparkles } from "lucide-react";
import { createGrokPane, type GrokPaneState } from "@/components/grok-pane";
import { GrokPanelGrid, GrokSinglePane } from "@/components/grok-panel-grid";
import { GrokHiddenStrip, GrokPanelSidebar } from "@/components/grok-panel-sidebar";
import { GrokPanelHeader } from "@/components/grok-panel-header";
import { JuniorJobsPanel } from "@/components/junior-jobs-panel";
import { JuniorMemoryPanel } from "@/components/junior-memory-panel";
import { useDictation } from "@/components/dictation";
import { CryptoUnlockGate } from "@/components/crypto-unlock-gate";
import { api, ApiError } from "@/lib/api";
import { isCryptoUnlocked } from "@/lib/message-crypto";
import { toast } from "sonner";
import { toastActionError } from "@/lib/toast-message";
import { INVALID_CHAT_TOAST, isConversationId } from "@/lib/chat-conversation";
import { comparePinned } from "@/lib/pin-order";
import type { GrokConversation, MessageCryptoStatus, TtsVoice } from "@/lib/types";
import { parseCustomNoteShelves, uniqueShelfId, type CustomNoteShelf, type FilingDestination } from "@/lib/custom-note-shelves";
import { saveGrokPanes } from "@/lib/grok-pane-storage";
import { clampPanelBox } from "@/lib/grok-panel-resize";
import {
  loadJuniorRailFlags,
  patchJuniorRailFlags,
  saveJuniorRailFlags,
  type JuniorRailFlags,
} from "@/lib/junior-rail";
import { WORK_IN_JUNIOR_EVENT, type WorkInJuniorDetail } from "@/lib/work-in-junior";
import { useSystemColorScheme } from "@/lib/system-theme";
import { RESIZE_HANDLES, usePanelDragResize } from "@/lib/usePanelDragResize";
import { useGrokPanels } from "@/lib/useGrokPanels";
import { useConversationPolling } from "@/lib/useConversationPolling";
import { useCryptoGate } from "@/lib/useCryptoGate";
import { cn } from "@/lib/utils";

export function GrokBubble({
  articleId,
  articleTitle,
  articleGuid,
  sourceRef,
  articleBody,
  onSavedNote,
  onStopArticleListen,
  onOpenArticle,
}: {
  articleId: string | null;
  articleTitle: string | null;
  articleGuid?: string | null;
  sourceRef?: string | null;
  articleBody?: string | null;
  onSavedNote: (noteId?: string, destination?: FilingDestination, folderId?: string | null) => Promise<void>;
  onStopArticleListen?: () => void;
  onOpenArticle?: (id: string) => void;
}) {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [noticeCount, setNoticeCount] = useState(0);
  const openRef = useRef(false);
  openRef.current = open;
  const seenMessageIdsRef = useRef(new Set<string>());
  const restoredConversationsRef = useRef(new Set<string>());
  const [fullscreen, setFullscreen] = useState(false);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const [ttsVoices, setTtsVoices] = useState<TtsVoice[]>([]);
  const [defaultTtsVoiceId, setDefaultTtsVoiceId] = useState("castor");
  const [sttEnabled, setSttEnabled] = useState(false);
  const [locked, setLocked] = useState(false);
  const dictation = useDictation();
  const [persist, setPersist] = useState(false);
  const [cryptoStatus, setCryptoStatus] = useState<MessageCryptoStatus | null>(null);
  const [chatModels, setChatModels] = useState<string[]>(["grok-4.6", "grok-4.7", "grok-4.3"]);
  const [customShelves, setCustomShelves] = useState<CustomNoteShelf[]>([]);
  const [listening, setListening] = useState(false);
  const [rail, setRail] = useState<JuniorRailFlags>(() => loadJuniorRailFlags());
  const systemScheme = useSystemColorScheme();
  const historyListRef = useRef<HTMLDivElement>(null);
  const jobsRailRef = useRef<HTMLElement | null>(null);
  const memoryRailRef = useRef<HTMLElement | null>(null);
  const activeListenStopRef = useRef<(() => void) | null>(null);

  const [renamingPaneId, setRenamingPaneId] = useState<string | null>(null);
  const [paneRenameDraft, setPaneRenameDraft] = useState("");
  const paneRenameInputRef = useRef<HTMLInputElement>(null);

  const cryptoGate = useCryptoGate(cryptoStatus);
  const {
    cryptoReady,
    setCryptoReady,
    showCryptoSetup,
    setShowCryptoSetup,
    messageCryptoEnabled,
    needsCryptoUnlock,
    showCryptoGate,
  } = cryptoGate;

  const panels = useGrokPanels(persist, setCustomShelves);
  const {
    panes,
    setPanes,
    focusedPaneId,
    setFocusedPaneId,
    focusedPaneIdRef,
    panesRef,
    addPane,
    openRemainderChat,
    removePane,
    updatePane,
    loadConversationInto,
    loadConversation,
    startNewChat,
    persistPaneLabels,
  } = panels;

  const focusedPane = panes.find((pane) => pane.id === focusedPaneId) ?? panes[0]!;

  const polling = useConversationPolling(
    persist,
    needsCryptoUnlock,
    panesRef,
    openRef,
    focusedPaneIdRef,
    seenMessageIdsRef,
    cryptoStatus,
    setNoticeCount,
    setOpen,
    setPanes,
    (conversationId: string) => loadConversation(conversationId, cryptoStatus, restoredConversationsRef.current),
  );
  const {
    conversations,
    setConversations,
    historyLoading,
    refreshHistory,
    renamingId,
    renameDraft,
    setRenameDraft,
    renameInputRef,
    startRename,
    cancelRename,
  } = polling;

  const dragResize = usePanelDragResize(mounted, fullscreen, open);
  const {
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
  } = dragResize;

  // ---- Effects (mounted, init, work-in-junior, etc.) ----

  useEffect(() => {
    function onWork(event: Event) {
      const detail = (event as CustomEvent<WorkInJuniorDetail>).detail;
      const noteId = detail?.noteId;
      if (!noteId) return;
      setOpen(true);
      setPanes((current) => {
        const focusId = focusedPaneIdRef.current;
        return current.map((pane) =>
          pane.id === focusId
            ? {
                ...pane,
                workingNoteId: noteId,
                workingNoteTitle: detail.title || pane.workingNoteTitle,
                includeArticle: false,
                includeNoteId: null,
                includeNoteTitle: null,
                includeOffset: 0,
                includeMode: "auto",
                includeHeading: null,
                conversationId: null,
                createNonce: null,
                messages: [],
                draft: "",
                savedNoteId: noteId,
              }
            : pane,
        );
      });
    }
    window.addEventListener(WORK_IN_JUNIOR_EVENT, onWork);
    return () => window.removeEventListener(WORK_IN_JUNIOR_EVENT, onWork);
  }, [setPanes]);

  useEffect(() => {
    if (open && persist) void refreshHistory();
  }, [open, persist, refreshHistory]);

  useEffect(() => {
    if (open) setNoticeCount(0);
  }, [open]);

  useEffect(() => {
    if (!open || typeof Notification === "undefined" || Notification.permission !== "default") return;
    void Notification.requestPermission();
  }, [open]);

  useEffect(() => {
    for (const pane of panes) {
      for (const message of pane.messages) {
        if (message.id) seenMessageIdsRef.current.add(message.id);
      }
    }
  }, [panes]);

  useEffect(() => {
    if (!mounted) return;
    saveGrokPanes(panes);
  }, [mounted, panes]);

  useEffect(() => {
    setMounted(true);
    api
      .chatStatus()
      .then((row) => {
        setEnabled(row.enabled);
        setLocked(Boolean(row.locked));
        setPersist(Boolean(row.persist ?? !row.locked));
        if (row.message_crypto) setCryptoStatus(row.message_crypto);
        if (row.models?.length) setChatModels(row.models);
        if (row.message_crypto?.enabled && isCryptoUnlocked()) setCryptoReady(true);
      })
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          router.replace("/login");
          return;
        }
        setEnabled(false);
        setLocked(false);
        setPersist(false);
      });
    Promise.all([
      api.tts().catch(() => ({ enabled: false, provider: "xai", default_voice_id: "castor", voices: [] as TtsVoice[] })),
      api.ttsVoices().catch(() => ({ default_voice_id: "castor", voices: [] as TtsVoice[] })),
    ]).then(([status, voicesPayload]) => {
      setTtsEnabled(status.enabled);
      const voices = voicesPayload.voices?.length ? voicesPayload.voices : status.voices ?? [];
      setTtsVoices(voices);
      setDefaultTtsVoiceId(
        voicesPayload.default_voice_id || status.default_voice_id || "castor",
      );
    });
    api
      .stt()
      .then((row) => setSttEnabled(row.enabled))
      .catch(() => setSttEnabled(false));
  }, [router, setCryptoReady]);

  useEffect(() => {
    if (!open) dictation?.stop();
  }, [open, dictation]);

  useEffect(() => {
    if (!mounted) return;
    saveJuniorRailFlags(rail);
  }, [mounted, rail]);

  useEffect(() => {
    if (!persist) return;
    for (const pane of panes) {
      const id = pane.conversationId;
      if (!id || pane.messages.length || restoredConversationsRef.current.has(id)) continue;
      restoredConversationsRef.current.add(id);
      void loadConversationInto(pane.id, id, cryptoStatus);
    }
  }, [loadConversationInto, panes, persist, cryptoStatus]);

  // ---- Conversation actions ----

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

  async function pinConversation(row: GrokConversation) {
    const pinned = !row.pinned;
    try {
      const updated = await api.patchChatConversation(row.id, { pinned });
      setConversations((current) => {
        const next = current.map((item) => (item.id === row.id ? { ...item, ...updated, pinned } : item));
        next.sort((a, b) =>
          comparePinned(a, b, (left, right) => (right.updated_at || "").localeCompare(left.updated_at || "")),
        );
        return next;
      });
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not pin that chat");
    }
  }

  async function deleteConversationAction(row: GrokConversation) {
    if (!window.confirm(`Delete "${row.title}"? This cannot be undone.`)) return;
    try {
      await api.deleteChatConversation(row.id);
      setConversations((current) => current.filter((item) => item.id !== row.id));
      const clearedFocused = focusedPane.conversationId === row.id;
      setPanes((current) =>
        current.map((pane) =>
          pane.conversationId === row.id
            ? { ...pane, conversationId: null, createNonce: null, messages: [], draft: "", recapQuestion: false, pendingAttachments: [], savedNoteId: null, conversationTitle: null }
            : pane,
        ),
      );
      if (clearedFocused) startNewChat();
      if (renamingId === row.id) {
        cancelRename();
      }
    } catch (error) {
      toastActionError(error, "delete chat", "Could not delete that chat");
    }
  }

  async function commitRename(conversationId: string) {
    if (!persist) return;
    if (!isConversationId(conversationId)) {
      toast.error(INVALID_CHAT_TOAST);
      return;
    }
    const draft = renameDraft;
    cancelRename();
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

  // ---- Pane rename ----

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

  // ---- Rail / listen ----

  function setRailFlag(patch: Partial<JuniorRailFlags>) {
    setRail((current) => patchJuniorRailFlags(current, patch));
  }

  function showHistoryList() {
    setRailFlag({ showChats: true });
    window.setTimeout(() => historyListRef.current?.scrollIntoView({ block: "nearest" }), 50);
  }

  function showJobsList() {
    setRailFlag({ showJobs: true });
    window.setTimeout(() => jobsRailRef.current?.scrollIntoView({ block: "nearest" }), 50);
  }

  function showMemoryList() {
    setRailFlag({ showMemory: true });
    window.setTimeout(() => memoryRailRef.current?.scrollIntoView({ block: "nearest" }), 50);
  }

  function handleActivateListen(stop: (() => void) | null) {
    activeListenStopRef.current = stop;
    setListening(Boolean(stop));
  }

  // ---- Fullscreen / panel close ----

  const exitFullscreen = useCallback(() => {
    setPanes((current) => {
      const keep = current.find((pane) => pane.id === focusedPaneId) ?? current[0];
      return keep ? [keep] : [createGrokPane(0)];
    });
    setFullscreen(false);
  }, [focusedPaneId, setPanes]);

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
  }, [dictation, exitFullscreen, fullscreen, listening, open, panelRef]);

  // ---- Render ----

  if (!mounted) return null;

  const bubbleLabel = focusedPane.displayName;
  const juniorThemeClass = systemScheme === "dark" ? "dark" : "";

  const bubble = (
    <button
      type="button"
      className="fixed z-[80] flex size-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg ring-1 ring-black/10"
      style={{ left: pos.x, top: pos.y }}
      aria-label={
        noticeCount > 0
          ? `Open ${bubbleLabel} chat, ${noticeCount} new message${noticeCount === 1 ? "" : "s"}`
          : `Open ${bubbleLabel} chat`
      }
      title={noticeCount > 0 ? `${bubbleLabel} — ${noticeCount} new` : bubbleLabel}
      onPointerDown={(event) => startBubbleDrag(event)}
      onClick={() => {
        if (movedRef.current) return;
        setOpen(true);
      }}
    >
      <Sparkles className="size-5" />
      {noticeCount > 0 ? (
        <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-white">
          {noticeCount > 9 ? "9+" : noticeCount}
        </span>
      ) : null}
    </button>
  );

  const panelBox = clampPanelBox(
    { left: pos.x, top: pos.y, w: size.w, h: size.h },
    window.innerWidth,
    window.innerHeight,
  );
  const subtitle =
    focusedPane.workingNoteTitle
      ? `Working note: ${focusedPane.workingNoteTitle}`
      : focusedPane.includeArticle && articleTitle
        ? `Connected: ${articleTitle}`
        : articleTitle
          ? "Thread only (article not included)"
          : "School coding help";

  const ownerRails = Boolean(fullscreen && persist && !locked);
  const showJobsPanel = Boolean(ownerRails && rail.showJobs);
  const showMemoryPanel = Boolean(ownerRails && rail.showMemory);
  const showChatsPanel = Boolean(persist && rail.showChats);
  const showHiddenStrip = Boolean(
    persist &&
      (!rail.showChats || (ownerRails && !rail.showJobs) || (ownerRails && !rail.showMemory)),
  );

  const panel = (
    <div
      ref={panelRef}
      className={cn(
        juniorThemeClass,
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
      <GrokPanelHeader
        focusedPaneDisplayName={focusedPane.displayName}
        subtitle={subtitle}
        fullscreen={fullscreen}
        locked={locked}
        panesLength={panes.length}
        persist={persist}
        messageCryptoEnabled={messageCryptoEnabled}
        renamingPaneId={renamingPaneId}
        focusedPaneId={focusedPaneId}
        paneRenameDraft={paneRenameDraft}
        setPaneRenameDraft={setPaneRenameDraft}
        paneRenameInputRef={paneRenameInputRef}
        startPaneRename={startPaneRename}
        commitPaneRename={commitPaneRename}
        cancelPaneRename={cancelPaneRename}
        addPane={() => addPane(locked)}
        exitFullscreen={exitFullscreen}
        toggleFullscreen={toggleFullscreen}
        closePanel={closePanel}
        setShowCryptoSetup={setShowCryptoSetup}
        onPanelDragStart={(event) => startPanelDrag(event, panelBox)}
      />

      <div className="flex min-h-0 flex-1 overflow-hidden">
        {showHiddenStrip ? (
          <GrokHiddenStrip
            showChats={rail.showChats}
            ownerRails={ownerRails}
            showJobs={rail.showJobs}
            showMemory={rail.showMemory}
            onStartNewChat={startNewChat}
            onShowHistory={showHistoryList}
            onShowJobs={showJobsList}
            onShowMemory={showMemoryList}
          />
        ) : null}
        {showChatsPanel ? (
          <GrokPanelSidebar
            conversations={conversations}
            historyLoading={historyLoading}
            focusedConversationId={focusedPane.conversationId}
            renamingId={renamingId}
            renameDraft={renameDraft}
            setRenameDraft={setRenameDraft}
            renameInputRef={renameInputRef}
            historyListRef={historyListRef}
            onStartNewChat={startNewChat}
            onLoadConversation={(id) => loadConversation(id, cryptoStatus, restoredConversationsRef.current)}
            onPinConversation={pinConversation}
            onDeleteConversation={deleteConversationAction}
            onStartRename={startRename}
            onCommitRename={commitRename}
            onCancelRename={cancelRename}
            onHide={() => setRailFlag({ showChats: false })}
          />
        ) : null}
        {showJobsPanel ? (
          <JuniorJobsPanel
            conversationId={focusedPane.conversationId}
            articleId={articleId}
            customShelves={customShelves}
            railRef={jobsRailRef}
            onHide={() => setRailFlag({ showJobs: false })}
            onRanConversation={(id) => {
              void loadConversation(id, cryptoStatus, restoredConversationsRef.current);
              void refreshHistory();
            }}
          />
        ) : null}
        {showMemoryPanel ? (
          <JuniorMemoryPanel railRef={memoryRailRef} onHide={() => setRailFlag({ showMemory: false })} />
        ) : null}
        {showCryptoGate ? (
          <CryptoUnlockGate
            enabled={messageCryptoEnabled}
            salt={cryptoStatus?.salt ?? null}
            onUnlocked={() => {
              setCryptoReady(true);
              setShowCryptoSetup(false);
              void api.chatStatus().then((row) => {
                if (row.message_crypto) setCryptoStatus(row.message_crypto);
              });
            }}
          />
        ) : fullscreen ? (
          <GrokPanelGrid
            panes={panes}
            focusedPaneId={focusedPaneId}
            compact={true}
            articleId={articleId}
            articleTitle={articleTitle}
            articleGuid={articleGuid}
            sourceRef={sourceRef}
            articleBody={articleBody}
            enabled={Boolean(enabled)}
            ttsEnabled={ttsEnabled}
            sttEnabled={sttEnabled}
            locked={locked}
            persist={persist}
            messageCryptoEnabled={messageCryptoEnabled}
            panelOpen={open}
            ttsVoices={ttsVoices}
            defaultTtsVoiceId={defaultTtsVoiceId}
            customShelves={customShelves}
            chatModels={chatModels}
            onSavedNote={onSavedNote}
            onStopArticleListen={onStopArticleListen}
            onOpenArticle={onOpenArticle}
            onActivateListen={handleActivateListen}
            onHistoryChanged={() => void refreshHistory()}
            onFocusPane={setFocusedPaneId}
            onUpdatePane={updatePane}
            onRemovePane={removePane}
            onCreateNoteShelf={createNoteShelf}
            onOpenRemainderChat={(remainder: string) => openRemainderChat(remainder, locked)}
            paneRenameProps={paneRenameProps}
          />
        ) : (
          <GrokSinglePane
            pane={focusedPane}
            articleId={articleId}
            articleTitle={articleTitle}
            articleGuid={articleGuid}
            sourceRef={sourceRef}
            articleBody={articleBody}
            enabled={Boolean(enabled)}
            ttsEnabled={ttsEnabled}
            sttEnabled={sttEnabled}
            locked={locked}
            persist={persist}
            messageCryptoEnabled={messageCryptoEnabled}
            panelOpen={open}
            ttsVoices={ttsVoices}
            defaultTtsVoiceId={defaultTtsVoiceId}
            customShelves={customShelves}
            chatModels={chatModels}
            onSavedNote={onSavedNote}
            onStopArticleListen={onStopArticleListen}
            onOpenArticle={onOpenArticle}
            onActivateListen={handleActivateListen}
            onHistoryChanged={() => void refreshHistory()}
            onFocusPane={setFocusedPaneId}
            onUpdatePane={updatePane}
            onCreateNoteShelf={createNoteShelf}
            onOpenRemainderChat={(remainder: string) => openRemainderChat(remainder, locked)}
            paneRenameProps={paneRenameProps}
          />
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
              onPointerDown={(event) => startResize(event, handle.edge, panelBox)}
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
