"use client";

import { createElement, useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle, Paperclip, Pencil, Save, Send, Sparkles, Square, X } from "lucide-react";
import { GrokRowMenu } from "@/components/grok-row-menu";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { useDictation } from "@/components/dictation";
import { DestinationSelect, FolderSelect } from "@/components/destination-controls";
import { JuniorMicControls, type JuniorMicMode, type JuniorMicPhase } from "@/components/junior-mic";
import { GrokChatMessage } from "@/components/grok-chat-message";
import { CalendarProposalCard } from "@/components/calendar-overlay";
import { MailProposalCard } from "@/components/mail-overlay";
import { GrokListenBar } from "@/components/grok-message-listen";
import { usePaneVoice } from "@/lib/usePaneVoice";
import { DEFAULT_PANE_NAME, defaultGrokPaneName, chatStatusLine, closeAssistantTurn, NO_REPLY_TOAST, normalizeTurnStatus, type ChatStatusKind, type ChatTurnStatus } from "@/lib/grok-pane-name";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { decryptStoredMessage, encryptMessageBody } from "@/lib/message-crypto";
import { savedReplyFillsEmptyBubble } from "@/lib/saved-reply";
import { agentFollowUpPending } from "@/lib/agent-followup";
import { destinationLabel, type CustomNoteShelf, type FilingDestination } from "@/lib/custom-note-shelves";
import { useNotePicker } from "@/lib/useNotePicker";
import { useNoteFiling } from "@/lib/useNoteFiling";
import { useSnippetRunner } from "@/lib/useSnippetRunner";
import { useRetryAssistant } from "@/lib/useRetryAssistant";
import { useImagineChat } from "@/lib/useImagineChat";
import { useChatSend } from "@/lib/useChatSend";
import { useStreamRunner } from "@/lib/useStreamRunner";
import { createContextHelpers } from "@/lib/context-helpers";
import { useModelSettings } from "@/lib/useModelSettings";
import { useNoteFolder } from "@/lib/useNoteFolder";
import { NotePickerDialog } from "@/components/note-picker-dialog";
import { loadLastFiling, saveLastFiling } from "@/lib/last-filing";
import {
  chatTimeoutToast,
  formatChatError,
  isOversizedPasteHttp,
  isSilentEmptyChatDetail,
  readableXaiToast,
  withAssistantName,
} from "@/lib/grok-chat-error";
import {
  INVALID_CHAT_TOAST,
  chatCreateErrorToast,
  conversationIdForRequest,
} from "@/lib/chat-conversation";
import {
  attachmentMarkdown,
  formatFileSize,
  LARRY_ATTACH_ACCEPT,
  LARRY_ATTACH_MAX_FILES,
  pendingToMessageFile,
  rejectLarryFile,
  snapshotFiles,
  uploadLarryAttachment,
  type LarryAttachment,
  type PendingAttachment,
} from "@/lib/larry-attach";
import { toastActionError, toastErrorFromUnknown } from "@/lib/toast-message";
import {
  chatContextOverCap,
  estimateChatContextChars,
  GROK_CONTEXT_CHAR_CAP,
  GROK_CONTEXT_THREAD_WINDOW,
  GROK_CONTEXT_TOAST,
  threadContextToast,
  JUNIOR_TEXTAREA_MAX_LENGTH,
  PASTE_FIRST_CHUNK_CHARS,
  pasteSplitToast,
  splitPasteChunk,
  textareaSelection,
} from "@/lib/grok-context";
import {
  articleNeedsIncludeSlice,
  parseSections,
  readerIncludeContext,
  resolveIncludeSlice,
  WORKING_NOTE_CHAR_CAP,
  type IncludeMode,
} from "@/lib/include-chunk";
import { isNoteShrinkMessage } from "@/lib/api-errors";
import { headingFromInstruction } from "@/lib/work-in-junior";
import { saveableThreadTurns, threadNoteMarkdown, threadNoteTitle } from "@/lib/junior-thread-note";
import { grokModelLabel, GROK_REASONING_EFFORTS, isGrokReasoningEffort, spendChipLabel } from "@/lib/grok-model";
import { postedSpendForTurn } from "@/lib/grok-auto-route";
import { hasMediaImage, imageToolIntent, MEDIA_MARKDOWN, thisTurnImageMediaIds } from "@/lib/chat-image";
import { DEFAULT_TTS_VOICE_ID, fallbackTtsVoices } from "@/lib/tts-defaults";
import { TTS_SPEEDS } from "@/lib/tts-preferences";
import { MIC_LIVE, MIC_STT_EMPTY_HINT, MIC_TRANSCRIBING } from "@/lib/stt-ui";
import type { Folder, TtsVoice } from "@/lib/types";
import { cn } from "@/lib/utils";

type ChatRole = "user" | "assistant";
export type ChatLine = {
  id: string;
  role: ChatRole;
  content: string;
  files?: LarryAttachment[];
  error?: string | null;
  failed?: boolean;
  waiting?: boolean;
  turnStatus?: ChatTurnStatus | null;
  routeLabel?: string | null;
  paceNote?: string | null;
  includeChip?: string | null;
  includeHasMore?: boolean;
  includeNextOffset?: number | null;
  includeNextHeading?: string | null;
  includeMode?: IncludeMode;
  includeHeading?: string | null;
  includeOffset?: number;
  calendarProposal?: { title: string; start: string; end: string; status?: "pending" | "wrote" | "error" };
  mailProposal?: { to: string; subject: string; body: string; status?: "pending" | "wrote" | "error" };
};

export type GrokPaneState = {
  id: string;
  displayName: string;
  conversationId: string | null;
  createNonce: string | null;
  modelChoice: string;
  lastResolvedModel: string | null;
  reasoningEffort: string;
  lastResolvedReasoning: string | null;
  messages: ChatLine[];
  draft: string;
  includeArticle: boolean;
  includeMode: IncludeMode;
  includeHeading: string | null;
  includeOffset: number;
  includeNoteId: string | null;
  includeNoteTitle: string | null;
  workingNoteId: string | null;
  workingNoteTitle: string | null;
  noteDest: FilingDestination;
  noteFolderId: string | null;
  recapQuestion: boolean;
  pendingAttachments: PendingAttachment[];
  streamStatus?: ChatStatusKind | null;
  savedNoteId: string | null;
  conversationTitle: string | null;
};

export { DEFAULT_PANE_NAME, defaultGrokPaneName };

type ListenTarget = { id: string; trigger: HTMLElement | null; script: string };

export function createGrokPane(paneIndex = 0): GrokPaneState {
  const last = loadLastFiling();
  return {
    id: crypto.randomUUID(),
    displayName: defaultGrokPaneName(paneIndex),
    conversationId: null,
    createNonce: null,
    modelChoice: "auto",
    lastResolvedModel: null,
    reasoningEffort: "low",
    lastResolvedReasoning: null,
    messages: [],
    draft: "",
    includeArticle: false,
    includeMode: "auto",
    includeHeading: null,
    includeOffset: 0,
    includeNoteId: null,
    includeNoteTitle: null,
    workingNoteId: null,
    workingNoteTitle: null,
    noteDest: last.dest,
    noteFolderId: last.folderId,
    recapQuestion: false,
    pendingAttachments: [],
    streamStatus: null,
    savedNoteId: null,
    conversationTitle: null,
  };
}

/** Keep controlled textarea in sync when STT inserts before React re-renders. */
function setNativeTextareaValue(el: HTMLTextAreaElement, value: string) {
  const desc = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
  desc?.set?.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

export function GrokPane({
  pane,
  label,
  compact,
  focused,
  canRemove,
  articleId,
  articleTitle,
  articleGuid: _articleGuid,
  sourceRef,
  articleBody,
  enabled,
  ttsEnabled,
  sttEnabled,
  locked,
  onFocus,
  onUpdate,
  onRemove,
  onSavedNote,
  onActivateListen,
  onStopArticleListen,
  onHistoryChanged,
  chatModels,
  persist,
  messageCryptoEnabled = false,
  panelOpen = true,
  ttsVoices = [],
  defaultTtsVoiceId = DEFAULT_TTS_VOICE_ID,
  renamingLabel = false,
  renameDraft = "",
  onStartRename,
  onRenameDraftChange,
  onCommitRename,
  onCancelRename,
  customShelves = [],
  onCreateNoteShelf,
  onOpenArticle,
  onOpenRemainderChat,
}: {
  pane: GrokPaneState;
  label: string;
  compact?: boolean;
  renamingLabel?: boolean;
  renameDraft?: string;
  onStartRename?: () => void;
  onRenameDraftChange?: (value: string) => void;
  onCommitRename?: () => void;
  onCancelRename?: () => void;
  customShelves?: CustomNoteShelf[];
  onCreateNoteShelf?: () => void | Promise<void>;
  onOpenArticle?: (id: string) => void;
  onOpenRemainderChat?: (remainder: string) => boolean;
  focused?: boolean;
  canRemove?: boolean;
  articleId: string | null;
  articleTitle: string | null;
  articleGuid?: string | null;
  sourceRef?: string | null;
  articleBody?: string | null;
  enabled: boolean;
  ttsEnabled: boolean;
  sttEnabled: boolean;
  locked: boolean;
  chatModels: string[];
  persist: boolean;
  messageCryptoEnabled?: boolean;
  onFocus: () => void;
  onUpdate: (updater: (pane: GrokPaneState) => GrokPaneState) => void;
  onRemove?: () => void;
  onSavedNote: (noteId?: string, destination?: FilingDestination, folderId?: string | null) => Promise<void>;
  onActivateListen: (stop: (() => void) | null) => void;
  onStopArticleListen?: () => void;
  onHistoryChanged?: () => void;
  panelOpen?: boolean;
  ttsVoices?: TtsVoice[];
  defaultTtsVoiceId?: string;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const stopRef = useRef<() => void>(() => {});
  const abortRef = useRef<AbortController | null>(null);
  const abortingRef = useRef(false);
  const inFlightRef = useRef(false);
  const turnIdRef = useRef(0);
  const dictation = useDictation();
  const draftValueRef = useRef(pane.draft);
  const draftNow = () => draftValueRef.current;
  useEffect(() => {
    draftValueRef.current = pane.draft;
  }, [pane.draft]);


  const [busy, setBusy] = useState(false);
  const messagesRef = useRef<ChatLine[]>(pane.messages);
  messagesRef.current = pane.messages;
  const bodyElementsRef = useRef(new Map<string, HTMLElement>());

  /* ── Voice hook ── */
  const voice = usePaneVoice({
    ttsEnabled,
    locked,
    panelOpen,
    busy,
    inFlightRef,
    onStopArticleListen,
    onActivateListen,
    paneMessages: pane.messages,
    messagesRef,
    bodyElementsRef,
    defaultTtsVoiceId,
    ttsVoices,
  });
  const [folders, setFolders] = useState<Folder[]>([]);
  const [uploadingFiles, setUploadingFiles] = useState(false);

  /* ── Chat creation refs ── */
  const createNonceRef = useRef<string | null>(null);
  const createInFlightRef = useRef<Promise<string> | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [streamStatus, setStreamStatus] = useState<ChatStatusKind | null>(null);
  const streamStatusRef = useRef<ChatStatusKind | null>(null);
  streamStatusRef.current = streamStatus;
  const [aborting, setAborting] = useState(false);
  const [inFlightSpend, setInFlightSpend] = useState<string | null>(null);
  const turnSpendRef = useRef({ model: "grok-4.6", reasoning: "low" });
  const [savingChat, setSavingChat] = useState(false);
  const shelfSelectId = `junior-shelf-${pane.id}`;
  const { addToNotes, applyToWorkingNote, saveChat } = useNoteFiling({
    folders,
    setFolders,
    patch,
    onSavedNote,
    pane,
    articleTitle,
    sourceRef,
    label,
    customShelves,
    shelfSelectId,
    savingChat,
    setSavingChat,
    busy,
    persist,
    toast,
    attachmentMarkdown,
    saveableThreadTurns,
    threadNoteTitle,
    threadNoteMarkdown,
    isNoteShrinkMessage,
    toastErrorFromUnknown,
  });
  const { runSnippet } = useSnippetRunner({
    onUpdate,
    onHistoryChanged,
    setBusy,
    spendChipLabel,
  });
  const notePicker = useNotePicker((noteId, noteTitle) => {
    patch({ includeNoteId: noteId, includeNoteTitle: noteTitle });
  });
  const thinkingTimerRef = useRef<number | null>(null);
  const gotDeltaRef = useRef(false);
  const generatingRef = useRef(false);
  const [readerCtx, setReaderCtx] = useState({ selection: "", heading: null as string | null });

  useEffect(() => {
    const sync = () => setReaderCtx(readerIncludeContext());
    document.addEventListener("selectionchange", sync);
    return () => document.removeEventListener("selectionchange", sync);
  }, []);

  const abortInFlight = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const applyStreamStatus = useCallback(
    (kind: ChatStatusKind | null) => {
      if (kind === "thinking" && gotDeltaRef.current) return;
      if (kind === "working" && (gotDeltaRef.current || generatingRef.current)) return;
      if (
        kind === "working" &&
        (streamStatusRef.current === "thinking" || streamStatusRef.current === "writing" || streamStatusRef.current === "queued")
      ) {
        return;
      }
      if (kind === "working" && streamStatusRef.current === "searching") {
        return;
      }
      const mapped: ChatStatusKind | null =
        kind === "working" ? "thinking" : kind;
      if (mapped === "writing" || mapped === "generating" || mapped === "searching" || mapped === "error" || mapped === "done" || mapped == null) {
        if (thinkingTimerRef.current != null) {
          window.clearTimeout(thinkingTimerRef.current);
          thinkingTimerRef.current = null;
        }
      }
      generatingRef.current = mapped === "generating";
      if (mapped === "queued" || mapped === "thinking") gotDeltaRef.current = false;
      setStreamStatus(mapped);
      const turn = normalizeTurnStatus(mapped);
      onUpdate((current) => ({
        ...current,
        streamStatus: mapped,
        messages:
          turn && turn !== "done"
            ? current.messages.map((item) =>
                item.waiting && item.role === "assistant"
                  ? { ...item, turnStatus: turn }
                  : item,
              )
            : current.messages,
      }));
    },
    [onUpdate],
  );

  const clearStreamStatus = useCallback(() => {
    if (thinkingTimerRef.current != null) {
      window.clearTimeout(thinkingTimerRef.current);
      thinkingTimerRef.current = null;
    }
    gotDeltaRef.current = false;
    setStreamStatus(null);
    onUpdate((current) => (current.streamStatus == null ? current : { ...current, streamStatus: null }));
  }, [onUpdate]);

  const { runImagineFromChat } = useImagineChat({
    pane, onUpdate, onHistoryChanged, label, applyStreamStatus, abortRef, abortingRef,
    setAborting, setBusy, setInFlightSpend, clearStreamStatus, spendChipLabel, hasMediaImage, formatChatError,
  });

  const failOpenTurn = useCallback(
    (assistantId?: string, aborted = false) => {
      setBusy(false);
      setAborting(false);
      abortingRef.current = false;
      onUpdate((current) => {
        const messages = current.messages.map((item) => {
          if (item.role !== "assistant") return item;
          const target = item.waiting || (assistantId && item.id === assistantId);
          if (!target) return item;
          const closed = closeAssistantTurn(item.content, {
            fileCount: item.files?.length,
            aborted,
          });
          return { ...item, ...closed };
        });
        const failed = messages.some(
          (item) => item.role === "assistant" && (item.waiting === false && item.failed) && (assistantId ? item.id === assistantId : true),
        );
        return {
          ...current,
          streamStatus: failed ? "error" : "done",
          messages,
        };
      });
      applyStreamStatus("error");
    },
    [applyStreamStatus, onUpdate],
  );

  const stopGeneration = useCallback(() => {
    dictation?.abort();
    turnIdRef.current += 1;
    inFlightRef.current = false;
    abortRef.current?.abort();
    abortRef.current = null;
    failOpenTurn(undefined, true);
    toast.error(NO_REPLY_TOAST);
  }, [dictation, failOpenTurn]);

  const markWriting = useCallback(() => {
    applyStreamStatus("writing");
  }, [applyStreamStatus]);

  const { runStream } = useStreamRunner({
    pane, onUpdate, onHistoryChanged, voice, abortRef, abortingRef, turnIdRef,
    setAborting, setBusy, setStreamStatus, setInFlightSpend, applyStreamStatus, clearStreamStatus,
    markWriting, ensureOwnedConversation, turnSpendRef, draftValueRef, gotDeltaRef, generatingRef,
    articleId, label, persist, messageCryptoEnabled, offerPasteSplit, postedSpendForTurn, spendChipLabel,
    conversationIdForRequest, INVALID_CHAT_TOAST, GROK_CONTEXT_THREAD_WINDOW, encryptMessageBody,
    decryptStoredMessage, MEDIA_MARKDOWN, formatChatError, chatCreateErrorToast, withAssistantName,
    isOversizedPasteHttp, PASTE_FIRST_CHUNK_CHARS, readableXaiToast, chatTimeoutToast,
    isSilentEmptyChatDetail, pasteSplitToast, hasMediaImage, toastActionError, savedReplyFillsEmptyBubble,
  });

  const { retryAssistant } = useRetryAssistant({
    pane, onUpdate, busy, aborting, abortingRef, enabled, inFlightRef, turnIdRef, abortRef,
    setAborting, setBusy, setStreamStatus, contextTooLarge, threadContextToast, contextInput,
    thisTurnImageMediaIds, imageToolIntent, runStream,
  });

  const { send, sendRef } = useChatSend({
    pane, onUpdate, enabled, busy, aborting, abortingRef, inFlightRef, setAborting, setBusy, setStreamStatus,
    turnIdRef, abortRef, toast, dictation, voice, readerCtx, articleId, articleTitle, articleBody,
    contextTooLarge, threadContextToast, contextInput, offerPasteSplit, thisTurnImageMediaIds, imageToolIntent,
    headingFromInstruction, resolveIncludeSlice, articleNeedsIncludeSlice, pendingToMessageFile, runStream, draftNow,
    PASTE_FIRST_CHUNK_CHARS, WORKING_NOTE_CHAR_CAP,
  });

  useEffect(() => {
    void api.folders().then(setFolders).catch(() => setFolders([]));
  }, []);


  useEffect(() => {
    if (!panelOpen) {
      abortInFlight();
      clearStreamStatus();
      setBusy(false);
      onUpdate((current) => ({
        ...current,
        messages: current.messages.map((item) =>
          item.waiting ? { ...item, waiting: false } : item,
        ),
      }));
    }
  }, [panelOpen, abortInFlight, clearStreamStatus, onUpdate]);

  useEffect(() => () => {
    abortInFlight();
    if (thinkingTimerRef.current != null) {
      window.clearTimeout(thinkingTimerRef.current);
      thinkingTimerRef.current = null;
    }
    gotDeltaRef.current = false;
    setStreamStatus(null);
  }, [abortInFlight]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      dictation?.abort();
      if (abortRef.current || busy || inFlightRef.current) {
        event.preventDefault();
        stopGeneration();
      }
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [busy, dictation, stopGeneration]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [pane.messages]);

  useEffect(() => {
    const el = draftRef.current;
    if (!el) return;
    el.style.height = "auto";
    const cap = Math.round(window.innerHeight * 0.6);
    el.style.height = `${Math.min(Math.max(el.scrollHeight, 48), cap)}px`;
  }, [pane.draft]);

  /** Re-read the live reply so playback never depends on stale state. */


  /** Sticky bar with no active target reads the newest assistant reply. */


  /** Same path as Listen, triggered when an assistant reply finishes streaming. */


  async function ensureOwnedConversation(): Promise<string> {
    const existing =
      conversationIdForRequest(pane.conversationId) ||
      conversationIdForRequest(pane.createNonce) ||
      conversationIdForRequest(createNonceRef.current);
    if (conversationIdForRequest(pane.conversationId)) {
      return pane.conversationId as string;
    }
    if (createInFlightRef.current) {
      return createInFlightRef.current;
    }
    const id = existing || crypto.randomUUID();
    createNonceRef.current = id;
    onUpdate((current) => (current.createNonce === id ? current : { ...current, createNonce: id }));
    const job = api
      .createChatConversation({
        id,
        model: pane.modelChoice,
        reasoning: pane.modelChoice === "auto" ? "auto" : pane.reasoningEffort,
      })
      .then((row) => {
        const created = conversationIdForRequest(row.id);
        if (!created) throw new ApiError(422, INVALID_CHAT_TOAST);
        onUpdate((current) => {
          if (current.createNonce !== id && current.conversationId !== created) return current;
          return {
            ...current,
            createNonce: created,
            conversationId: created,
          };
        });
        return created;
      });
    createInFlightRef.current = job;
    try {
      return await job;
    } finally {
      if (createInFlightRef.current === job) createInFlightRef.current = null;
    }
  }

  async function attachFiles(fileList: FileList | File[]) {
    const incoming = snapshotFiles(fileList);
    if (!incoming.length) return;
    if (locked || !enabled) {
      toast.error("Chat is not available for attachments right now.");
      return;
    }
    const already = pane.pendingAttachments ?? [];
    const room = LARRY_ATTACH_MAX_FILES - already.length;
    if (room <= 0) {
      toast.error(`Attach up to ${LARRY_ATTACH_MAX_FILES} files.`);
      return;
    }
    const chosen = incoming.slice(0, room);
    if (incoming.length > room) {
      toast.error(`Attach up to ${LARRY_ATTACH_MAX_FILES} files.`);
    }
    setUploadingFiles(true);
    try {
      for (const file of chosen) {
        const reason = rejectLarryFile(file);
        if (reason) {
          toast.error(reason);
          continue;
        }
        const uploaded = await uploadLarryAttachment(file);
        if (!uploaded.id) {
          toast.error("No attach without a media id.");
          continue;
        }
        onUpdate((current) => {
          const pending = current.pendingAttachments ?? [];
          if (pending.some((item) => item.id === uploaded.id)) return current;
          if (pending.length >= LARRY_ATTACH_MAX_FILES) return current;
          return { ...current, pendingAttachments: [...pending, uploaded] };
        });
      }
    } catch (error) {
      toastActionError(error, "attach that file", "Could not attach that file");
    } finally {
      setUploadingFiles(false);
    }
  }

  function removePending(mediaId: string) {
    onUpdate((current) => ({
      ...current,
      pendingAttachments: (current.pendingAttachments ?? []).filter((item) => item.id !== mediaId),
    }));
    void api.deleteNoteMedia(mediaId).catch(() => {
      /* still drop the chip */
    });
  }

  function plannedWorkingSlice() {
    if (!pane.workingNoteId) return null;
    const body = pane.workingNoteId === articleId ? articleBody || "" : "";
    if (!body) return null;
    const over = articleNeedsIncludeSlice(body, WORKING_NOTE_CHAR_CAP);
    const mode: IncludeMode =
      pane.includeMode && pane.includeMode !== "auto"
        ? pane.includeMode
        : over
          ? "chunk"
          : "auto";
    return resolveIncludeSlice({
      body,
      mode,
      heading: pane.includeHeading,
      offset: pane.includeOffset,
      title: pane.workingNoteTitle || articleTitle,
      cap: WORKING_NOTE_CHAR_CAP,
      hardMax: WORKING_NOTE_CHAR_CAP,
    });
  }

  function plannedIncludeSlice() {
    if (!pane.includeArticle || !articleId) return null;
    const mode: IncludeMode =
      (pane.includeMode && pane.includeMode !== "auto"
        ? pane.includeMode
        : articleNeedsIncludeSlice(articleBody)
          ? "chunk"
          : "auto") as IncludeMode;
    return resolveIncludeSlice({
      body: articleBody || "",
      mode,
      selection: pane.includeMode === "selection" ? readerCtx.selection : undefined,
      heading: pane.includeHeading,
      offset: pane.includeOffset,
      title: articleTitle,
    });
  }

  const contextHelpers = createContextHelpers({
    pane, articleId, articleBody, plannedIncludeSlice, plannedWorkingSlice,
    chatContextOverCap, estimateChatContextChars, GROK_CONTEXT_CHAR_CAP, PASTE_FIRST_CHUNK_CHARS,
    pasteSplitToast, splitPasteChunk, textareaSelection, draftRef, readerCtx, onOpenRemainderChat,
    send, Button, createElement,
  });

  function contextInput(draft: string, extraMessages: ChatLine[] = pane.messages) {
    return contextHelpers.contextInput(draft, extraMessages);
  }

  function contextTooLarge(draft: string, extraMessages: ChatLine[] = pane.messages) {
    return contextHelpers.contextTooLarge(draft, extraMessages);
  }

  function offerPasteSplit(draft: string) {
    contextHelpers.offerPasteSplit(draft);
  }

  const fillComposerDraft = useCallback(
    (transcript: string, focus = false) => {
      const message = transcript.trim();
      if (!message) return;
      draftValueRef.current = message;
      onUpdate((current) => ({ ...current, draft: message }));
      const el = draftRef.current;
      if (el) {
        setNativeTextareaValue(el, message);
        el.style.height = "auto";
        const cap = Math.round(window.innerHeight * 0.6);
        el.style.height = `${Math.min(Math.max(el.scrollHeight, 48), cap)}px`;
        if (focus) {
          el.focus();
          const end = message.length;
          el.setSelectionRange(end, end);
        }
      }
    },
    [onUpdate],
  );

  const submitVoiceTranscript = useCallback(
    (transcript: string) => {
      const message = transcript.trim();
      if (!message) return;
      fillComposerDraft(message);
      void sendRef.current({ message, fromStt: true });
    },
    [fillComposerDraft],
  );

  const applySttDraft = useCallback(
    (transcript: string) => {
      fillComposerDraft(transcript, true);
    },
    [fillComposerDraft],
  );


  async function imagine() {
    const prompt = draftNow().trim();
    if (!prompt) {
      toast.error("Type a prompt for the image.");
      return;
    }
    if (busy || aborting || abortingRef.current || !enabled || locked || inFlightRef.current) return;
    inFlightRef.current = true;
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    applyStreamStatus("working");
    try {
      const pendingImages = (pane.pendingAttachments ?? [])
        .filter((item) => item.kind === "image" && item.id)
        .map((item) => item.id);
      const result = await api.chatImagine(
        {
          prompt,
          conversation_id: pane.conversationId,
          media_ids: pendingImages.length ? pendingImages : undefined,
        },
        controller.signal,
      );
      const reply = result.assistant_message;
      const hasPixels =
        hasMediaImage(reply.content || "") ||
        (reply.files || []).some((file) => file.kind === "image" && file.media_id);
      if (!hasPixels) {
        throw new ApiError(502, "Could not generate that image.");
      }
      onUpdate((current) => ({
        ...current,
        draft: "",
        conversationId: result.conversation_id || current.conversationId,
        streamStatus: null,
        messages: [
          ...current.messages,
          {
            id: result.user_message.id,
            role: "user",
            content: result.user_message.content || "",
            files: result.user_message.files,
          },
          {
            id: result.assistant_message.id,
            role: "assistant",
            content: result.assistant_message.content || "",
            files: result.assistant_message.files,
          },
        ],
      }));
      onHistoryChanged?.();
    } catch (error) {
      if (controller.signal.aborted) {
        onUpdate((current) => (current.streamStatus == null ? current : { ...current, streamStatus: null }));
        return;
      }
      toastErrorFromUnknown(error, "Could not generate that image.");
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      abortingRef.current = false;
      setAborting(false);
      setBusy(false);
      clearStreamStatus();
      inFlightRef.current = false;
    }
  }

  function patch(partial: Partial<GrokPaneState>) {
    onUpdate((current) => ({ ...current, ...partial }));
  }

  const { setModelChoice, setReasoningEffort, setRecapQuestion } = useModelSettings({
    pane, persist, patch, isGrokReasoningEffort, onHistoryChanged,
  });

  const { createNoteFolder, handleNoteDestChange } = useNoteFolder({
    pane, customShelves, destinationLabel, setFolders, patch, saveLastFiling,
  });

  const modelOptions = ["auto", ...chatModels.filter((item, index, all) => all.indexOf(item) === index)];
  const voiceOptions = ttsVoices.length ? ttsVoices : fallbackTtsVoices();
  const hasReadableReply = pane.messages.some((item) => item.role === "assistant" && Boolean(item.content));
  const showStickyPlayer = ttsEnabled && !locked && (voice.listen.isActive || hasReadableReply);
  const visibleStatus = pane.streamStatus ?? streamStatus;
  const lastAssistantId = [...pane.messages].reverse().find((item) => item.role === "assistant")?.id ?? null;
  const canSaveChat = saveableThreadTurns(pane.messages).length > 0;
  const headerSelectClass =
    "h-7 max-w-[7rem] rounded-md border border-input bg-background px-1.5 text-[11px] text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50";

  return (
    <div
      className={cn(
        "flex min-h-0 flex-col overflow-hidden",
        compact ? "h-full" : "h-full min-h-0 flex-1",
        focused && compact ? "ring-1 ring-inset ring-primary/40" : "",
      )}
      onPointerDown={onFocus}
    >
      {compact ? (
        <div className="flex shrink-0 items-center gap-1 border-b px-2 py-1.5">
          <div className="min-w-0 flex-1">
            {renamingLabel ? (
              <Input
                value={renameDraft}
                className="h-7 px-2 text-xs"
                aria-label="Rename pane"
                autoFocus
                onChange={(event) => onRenameDraftChange?.(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    onCommitRename?.();
                  }
                  if (event.key === "Escape") {
                    event.preventDefault();
                    onCancelRename?.();
                  }
                }}
                onBlur={() => onCommitRename?.()}
              />
            ) : (
              <>
                <button
                  type="button"
                  className="truncate text-left text-xs font-medium hover:underline"
                  title="Rename pane"
                  onClick={() => onStartRename?.()}
                >
                  {label}
                </button>
                <p className="truncate text-[10px] text-muted-foreground">
                  {grokModelLabel(pane.modelChoice, pane.lastResolvedModel, pane.lastResolvedReasoning)}
                </p>
              </>
            )}
          </div>
          {!renamingLabel && onStartRename ? (
            <GrokRowMenu
              label={label}
              items={[
                {
                  key: "rename-pane",
                  label: "Rename pane",
                  icon: <Pencil className="size-3.5" />,
                  onSelect: () => onStartRename(),
                },
              ]}
            />
          ) : null}
          {canRemove ? (
            <Button size="icon-xs" variant="ghost" onClick={onRemove} aria-label={`Remove ${label}`}>
              <X className="size-3.5" />
            </Button>
          ) : null}
        </div>
      ) : null}

      <div className="flex shrink-0 flex-wrap items-center gap-x-2 gap-y-1 border-b px-2 py-1.5 text-xs">
        <label className="inline-flex items-center gap-1">
          <span className="text-muted-foreground">Model</span>
          <select
            aria-label={`Model for ${label}`}
            value={pane.modelChoice}
            disabled={!enabled}
            onChange={(event) => void setModelChoice(event.target.value)}
            className={headerSelectClass}
          >
            {modelOptions.map((item) => (
              <option key={item} value={item}>
                {item === "auto" ? "Auto" : item}
              </option>
            ))}
          </select>
        </label>
        <label className="inline-flex items-center gap-1">
          <span className="text-muted-foreground">Reasoning</span>
          <select
            aria-label={`Reasoning for ${label}`}
            value={pane.modelChoice === "auto" ? "auto" : pane.reasoningEffort}
            disabled={!enabled || pane.modelChoice === "auto"}
            onChange={(event) => void setReasoningEffort(event.target.value)}
            className={headerSelectClass}
          >
            {pane.modelChoice === "auto" ? (
              <option value="auto">Auto</option>
            ) : (
              GROK_REASONING_EFFORTS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))
            )}
          </select>
        </label>
        {ttsEnabled && !locked && !showStickyPlayer ? (
          <>
            <label className="inline-flex items-center gap-1">
              <span className="text-muted-foreground">Voice</span>
              <select
                aria-label="TTS voice"
                value={voice.voiceId}
                onChange={(event) => voice.handleVoiceChange(event.target.value)}
                className={headerSelectClass}
              >
                {voiceOptions.map((voice) => (
                  <option key={voice.voice_id} value={voice.voice_id}>
                    {voice.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="inline-flex items-center gap-1">
              <span className="text-muted-foreground">Speed</span>
              <select
                aria-label="Playback speed"
                value={voice.playbackSpeed}
                onChange={(event) => voice.handleSpeedChange(Number(event.target.value))}
                className={cn(headerSelectClass, "max-w-[4rem]")}
              >
                {TTS_SPEEDS.map((rate) => (
                  <option key={rate} value={rate}>
                    {rate === 1 ? "1×" : `${rate}×`}
                  </option>
                ))}
              </select>
            </label>
          </>
        ) : null}
        <label className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
          <input
            type="checkbox"
            checked={pane.recapQuestion}
            disabled={!enabled}
            onChange={(event) => void setRecapQuestion(event.target.checked)}
          />
          Recap my question
        </label>
        <DestinationSelect
          id={shelfSelectId}
          value={pane.noteDest}
          onChange={handleNoteDestChange}
          customShelves={customShelves}
          onCreateShelf={onCreateNoteShelf}
          className="max-w-[6.5rem] text-[11px]"
        />
        <FolderSelect
          shelf={pane.noteDest}
          folders={folders}
          value={pane.noteFolderId}
          onChange={(next) => {
            patch({ noteFolderId: next });
            saveLastFiling(pane.noteDest, next);
          }}
          onCreateFolder={() => void createNoteFolder()}
          className="max-w-[6.5rem] text-[11px]"
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-7"
          disabled={!canSaveChat || savingChat || busy}
          aria-label="Save chat"
          title={
            busy
              ? "Wait until Junior finishes, then save this chat into a folder"
              : canSaveChat
                ? "Save this finished chat into the shelf and folder"
                : "Nothing to save"
          }
          onClick={() => void saveChat()}
        >
          <Save className="size-3.5" />
          {savingChat ? "Saving…" : "Save chat"}
        </Button>
      </div>

      {agentFollowUpPending(pane.messages) ? (
        <p
          role="status"
          aria-live="polite"
          className="shrink-0 border-b bg-muted px-3 py-2 text-sm font-medium text-foreground"
        >
          Cloud Agent is running in this chat. The result will show up here.
        </p>
      ) : null}

      {visibleStatus && visibleStatus !== "done" && visibleStatus !== "error" ? (
        <p
          data-junior-status={visibleStatus}
          role="status"
          aria-live="polite"
          className="shrink-0 border-b bg-muted px-3 py-2 text-sm font-medium text-foreground"
        >
          {chatStatusLine(label, visibleStatus)}
        </p>
      ) : null}

      <div ref={listRef} className="relative min-h-0 flex-1 overflow-y-auto overscroll-contain">
        {showStickyPlayer ? (
          <GrokListenBar
            phase={voice.listen.phase}
            disabled={!ttsEnabled || locked}
            speed={voice.listen.speed}
            voiceId={voice.voiceId}
            voices={voiceOptions}
            onListen={voice.listenLatestReply}
            onFromHere={voice.listenFromHere}
            onPause={voice.handleListenPause}
            onStop={voice.handleListenStop}
            onSpeedChange={voice.handleSpeedChange}
            onVoiceChange={voice.handleVoiceChange}
          />
        ) : null}
        <div className="space-y-3 px-3 py-3">
          {pane.messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {pane.workingNoteId
                ? `Type instructions only. Junior already has “${pane.workingNoteTitle || "this note"}” on the server.`
                : pane.includeArticle && articleId
                  ? "Ask about this article or school coding."
                  : "Ask for school coding help — explanations, debugging, or fenced code."}
            </p>
          ) : (
            pane.messages.map((item) => (
              <div key={item.id}>
              <GrokChatMessage
                key={item.id}
                id={item.id}
                role={item.role}
                content={item.content}
                error={item.error}
                failed={item.failed}
                waiting={item.waiting}
                busy={busy}
                ttsAvailable={ttsEnabled && !locked}
                listening={voice.listenTarget?.id === item.id && voice.listen.isActive}
                activeWord={voice.listenTarget?.id === item.id ? voice.activeWord : null}
                assistantName={label}
                files={item.files}
                wordEnabled={!locked}
                noteDest={pane.noteDest}
                noteFolderId={pane.noteFolderId}
                folders={folders}
                customShelves={customShelves}
                onCreateNoteShelf={onCreateNoteShelf}
                onCreateFolder={(shelf) => void createNoteFolder(shelf)}
                onRememberFiling={(dest, folderId) => {
                  patch({ noteDest: dest, noteFolderId: folderId });
                  saveLastFiling(dest, folderId);
                }}
                conversationId={pane.conversationId}
                articleId={articleId}
                schoolEnabled={!locked}
                onSchoolAssistant={(message) => {
                  onUpdate((current) => {
                    if (current.messages.some((row) => row.id === message.id)) return current;
                    return {
                      ...current,
                      conversationId: current.conversationId,
                      messages: [
                        ...current.messages,
                        { id: message.id, role: "assistant", content: message.content || "", files: message.files },
                      ],
                    };
                  });
                  onHistoryChanged?.();
                }}
                routeLabel={item.role === "assistant" ? item.routeLabel : null}
                paceNote={item.role === "assistant" ? item.paceNote : null}
                includeChip={item.includeChip}
                onNextChunk={
                  item.role === "assistant" && item.id === lastAssistantId && item.includeHasMore && !busy
                    ? () =>
                        void send({
                          message: item.includeNextHeading
                            ? `Continue with the next section: ${item.includeNextHeading}`
                            : "Continue with the next chunk.",
                          includeMode: item.includeNextHeading ? "heading" : "chunk",
                          includeHeading: item.includeNextHeading,
                          includeOffset: item.includeNextOffset ?? pane.includeOffset,
                        })
                    : undefined
                }
                statusLine={
                  item.role !== "assistant"
                    ? null
                    : item.failed || item.turnStatus === "error"
                      ? chatStatusLine(label, "error")
                      : item.turnStatus && item.turnStatus !== "done"
                        ? chatStatusLine(label, item.turnStatus)
                        : item.waiting ||
                            (Boolean(visibleStatus) &&
                              visibleStatus !== "done" &&
                              item.id === lastAssistantId)
                          ? chatStatusLine(
                              label,
                              visibleStatus || item.turnStatus || (item.waiting ? "thinking" : "writing"),
                            )
                          : null
                }
                onRegisterBody={voice.registerBody}
                onListen={voice.requestListen}
                onTtsWordPick={(messageId, index) => {
                  voice.clickedWordRef.current = { messageId, index };
                }}
                onAddToNotes={(payload) => void addToNotes(payload, item.id)}
                onApplyToNote={
                  pane.workingNoteId && item.role === "assistant" && item.content.trim()
                    ? () => void applyToWorkingNote(item.content, item.id)
                    : undefined
                }
                onRetry={item.role === "assistant" && item.failed ? () => void retryAssistant(item.id) : undefined}
                onRunSnippet={(messageId, code) => void runSnippet(messageId, code)}
                onOpenArticle={onOpenArticle}
              />
              {item.calendarProposal ? (
                <CalendarProposalCard
                  proposal={item.calendarProposal}
                  onWrote={(status) =>
                    onUpdate((current) => ({
                      ...current,
                      messages: current.messages.map((row) =>
                        row.id === item.id && row.calendarProposal
                          ? { ...row, calendarProposal: { ...row.calendarProposal, status } }
                          : row,
                      ),
                    }))
                  }
                />
              ) : null}
              {item.mailProposal ? (
                <MailProposalCard
                  proposal={item.mailProposal}
                  onWrote={(status) =>
                    onUpdate((current) => ({
                      ...current,
                      messages: current.messages.map((row) =>
                        row.id === item.id && row.mailProposal
                          ? { ...row, mailProposal: { ...row.mailProposal, status } }
                          : row,
                      ),
                    }))
                  }
                />
              ) : null}
              </div>
            ))
          )}
        </div>
      </div>

      {locked ? (
        <p className="shrink-0 border-t px-3 py-2 text-xs text-muted-foreground">
          Demo accounts cannot use chat, dictation, or Listen.
        </p>
      ) : enabled === false ? (
        <p className="shrink-0 border-t px-3 py-2 text-xs text-muted-foreground">
          Chat is off until XAI_API_KEY is set on Railway. It never lives in the browser.
        </p>
      ) : null}
      <form
        className={cn(
          "flex shrink-0 flex-col gap-1.5 border-t p-2",
          dragOver && "bg-primary/5",
        )}
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
        onDragEnter={(event) => {
          event.preventDefault();
          if (enabled && !locked) setDragOver(true);
        }}
        onDragOver={(event) => {
          event.preventDefault();
          if (enabled && !locked) setDragOver(true);
        }}
        onDragLeave={(event) => {
          if (event.currentTarget.contains(event.relatedTarget as Node)) return;
          setDragOver(false);
        }}
        onDrop={(event) => {
          event.preventDefault();
          setDragOver(false);
          void attachFiles(snapshotFiles(event.dataTransfer.files));
        }}
        onPaste={(event) => {
          const picked = snapshotFiles(event.clipboardData?.files);
          if (!picked.length) return;
          event.preventDefault();
          void attachFiles(picked);
        }}
      >
        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
            <label className="inline-flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={pane.includeArticle}
                disabled={!articleId}
                onChange={(event) => {
                  const on = event.target.checked;
                  patch({
                    includeArticle: on,
                    includeMode: on && articleNeedsIncludeSlice(articleBody) ? "chunk" : "auto",
                    includeOffset: 0,
                  });
                }}
              />
              Include current article
            </label>
            <label className="inline-flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={Boolean(pane.includeNoteId) || notePicker.notePickerOpen}
                onChange={(event) => {
                  if (event.target.checked) {
                    notePicker.openPicker();
                    return;
                  }
                  notePicker.closePicker();
                  patch({ includeNoteId: null, includeNoteTitle: null });
                }}
              />
              Include note…
            </label>
            <label className="inline-flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={voice.autoReadReplies}
                disabled={!ttsEnabled || locked}
                onChange={(event) => {
                  const on = event.target.checked;
                  voice.setAutoReadReplies(on);
                  voice.writeStoredTtsAutoRead(on);
                  if (!on && voice.listen.isActive) {
                    voice.listen.stop();
                  }
                }}
              />
              Read replies
            </label>
            {pane.workingNoteTitle ? (
              <span className="inline-flex max-w-full items-center gap-1 rounded-full border bg-muted/40 px-2 py-0.5">
                <span className="truncate">Working: {pane.workingNoteTitle}</span>
                <button
                  type="button"
                  className="rounded-full p-0.5 hover:bg-background"
                  aria-label="Stop working on that note"
                  onClick={() => patch({ workingNoteId: null, workingNoteTitle: null })}
                >
                  <X className="size-3" />
                </button>
              </span>
            ) : null}
            {pane.includeNoteTitle ? (
              <span className="inline-flex max-w-full items-center gap-1 rounded-full border bg-muted/40 px-2 py-0.5">
                <span className="truncate">{pane.includeNoteTitle}</span>
                <button
                  type="button"
                  className="rounded-full p-0.5 hover:bg-background"
                  aria-label="Stop including that note"
                  onClick={() => {
                    notePicker.closePicker();
                    patch({ includeNoteId: null, includeNoteTitle: null });
                  }}
                >
                  <X className="size-3" />
                </button>
              </span>
            ) : null}
          </div>
          {pane.includeArticle && articleId && articleNeedsIncludeSlice(articleBody) ? (
            <div className="rounded-md border bg-muted/20 p-1.5 text-[11px] text-foreground">
              <p className="text-muted-foreground">This note is too large to send whole. Include a slice:</p>
              <div className="mt-1 flex flex-wrap items-center gap-1">
                <Button
                  type="button"
                  size="xs"
                  variant={pane.includeMode === "selection" ? "secondary" : "outline"}
                  disabled={!readerCtx.selection}
                  onClick={() => patch({ includeMode: "selection", includeOffset: 0 })}
                >
                  Include selection
                </Button>
                <select
                  className="h-7 max-w-[14rem] rounded-md border bg-background px-1 text-[11px]"
                  aria-label="Include this heading"
                  value={pane.includeMode === "heading" ? pane.includeHeading || "" : ""}
                  onChange={(event) => {
                    const heading = event.target.value;
                    patch({
                      includeMode: heading ? "heading" : "chunk",
                      includeHeading: heading || null,
                      includeOffset: 0,
                    });
                  }}
                >
                  <option value="">Include this heading…</option>
                  {(readerCtx.heading
                    ? [
                        readerCtx.heading,
                        ...parseSections(articleBody || "")
                          .map((item) => item.title)
                          .filter((title) => title !== "Opening" && title !== readerCtx.heading),
                      ]
                    : parseSections(articleBody || "")
                        .map((item) => item.title)
                        .filter((title) => title !== "Opening")
                  )
                    .filter((title, index, all) => all.indexOf(title) === index)
                    .map((title) => (
                      <option key={title} value={title}>
                        {title}
                      </option>
                    ))}
                </select>
                <Button
                  type="button"
                  size="xs"
                  variant={pane.includeMode === "chunk" || pane.includeMode === "auto" ? "secondary" : "outline"}
                  onClick={() => patch({ includeMode: "chunk", includeOffset: 0, includeHeading: null })}
                >
                  First chunk + next
                </Button>
              </div>
            </div>
          ) : null}
          {pane.workingNoteId &&
          pane.workingNoteId === articleId &&
          articleNeedsIncludeSlice(articleBody, WORKING_NOTE_CHAR_CAP) ? (
            <div className="rounded-md border bg-muted/20 p-1.5 text-[11px] text-foreground">
              <p className="text-muted-foreground">This note is over 80k characters. Junior gets a heading or chunk — not the textarea.</p>
              <div className="mt-1 flex flex-wrap items-center gap-1">
                <select
                  className="h-7 max-w-[14rem] rounded-md border bg-background px-1 text-[11px]"
                  aria-label="Work on this heading"
                  value={pane.includeMode === "heading" ? pane.includeHeading || "" : ""}
                  onChange={(event) => {
                    const heading = event.target.value;
                    patch({
                      includeMode: heading ? "heading" : "chunk",
                      includeHeading: heading || null,
                      includeOffset: 0,
                    });
                  }}
                >
                  <option value="">This heading…</option>
                  {parseSections(articleBody || "")
                    .map((item) => item.title)
                    .filter((title) => title !== "Opening")
                    .filter((title, index, all) => all.indexOf(title) === index)
                    .map((title) => (
                      <option key={title} value={title}>
                        {title}
                      </option>
                    ))}
                </select>
                <Button
                  type="button"
                  size="xs"
                  variant={pane.includeMode === "chunk" || pane.includeMode === "auto" ? "secondary" : "outline"}
                  onClick={() => patch({ includeMode: "chunk", includeOffset: 0, includeHeading: null })}
                >
                  First chunk + next
                </Button>
              </div>
            </div>
          ) : null}
          {plannedWorkingSlice()?.chip ? (
            <span className="inline-flex max-w-full items-center rounded-full border bg-muted/40 px-2 py-0.5 text-[11px]">
              {plannedWorkingSlice()?.chip}
            </span>
          ) : null}
          {pane.includeArticle && plannedIncludeSlice()?.chip ? (
            <span className="inline-flex max-w-full items-center rounded-full border bg-muted/40 px-2 py-0.5 text-[11px]">
              {plannedIncludeSlice()?.chip}
            </span>
          ) : null}
          <NotePickerDialog
            open={notePicker.notePickerOpen}
            query={notePicker.noteQuery}
            choices={notePicker.noteChoices}
            loading={notePicker.loadingNotes}
            onQueryChange={notePicker.setNoteQuery}
            onSelect={notePicker.selectNote}
            onClose={notePicker.closePicker}
          />
        </div>
        {(pane.pendingAttachments ?? []).filter((file) => file.id).length || uploadingFiles ? (
          <ul className="flex flex-wrap gap-1.5" aria-label="Files to send">
            {(pane.pendingAttachments ?? [])
              .filter((file) => file.id)
              .map((file) => (
              <li
                key={file.id}
                className="inline-flex max-w-full items-center gap-1 rounded-full border bg-muted/40 py-0.5 pl-0.5 pr-2 text-[11px]"
              >
                {file.kind === "image" && file.url ? (
                  <img src={file.url} alt="" className="size-5 shrink-0 rounded-full object-cover" />
                ) : (
                  <Paperclip className="ml-1.5 size-3 shrink-0 text-muted-foreground" aria-hidden="true" />
                )}
                <span className="truncate">{file.name}</span>
                <span className="shrink-0 font-mono text-[10px] text-muted-foreground" title={file.id}>
                  {file.id}
                </span>
                <span className="shrink-0 text-muted-foreground">{formatFileSize(file.size)}</span>
                <button
                  type="button"
                  className="rounded-full p-0.5 hover:bg-background"
                  aria-label={`Remove ${file.name}`}
                  onClick={() => removePending(file.id)}
                >
                  <X className="size-3" />
                </button>
              </li>
            ))}
            {uploadingFiles ? (
              <li className="inline-flex items-center gap-1 rounded-full border bg-muted/40 px-2 py-0.5 text-[11px] text-muted-foreground">
                <LoaderCircle className="size-3 animate-spin" />
                Uploading…
              </li>
            ) : null}
          </ul>
        ) : null}
        <div className="flex min-w-0 flex-nowrap items-center gap-2">
          <Textarea
            ref={draftRef}
            dictate={false}
            maxLength={JUNIOR_TEXTAREA_MAX_LENGTH}
            className="min-h-12 max-h-[min(60vh,28rem)] min-w-0 flex-1 resize-y rounded-md border bg-background px-2 py-1.5 text-sm"
            value={pane.draft}
            onChange={(event) => {
              voice.clearSttEmptyHint();
              draftValueRef.current = event.target.value;
              patch({ draft: event.target.value });
            }}
            placeholder={
              pane.workingNoteId
                ? "Instructions only — the note is already on the server…"
                : pane.includeArticle && articleId
                  ? "Ask about this article or school coding…"
                  : `Ask ${label} for school coding help…`
            }
            disabled={!enabled}
            onFocus={() => {
              onFocus();
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void send();
              }
            }}
          />
          <input
            ref={fileInputRef}
            type="file"
            className="sr-only"
            accept={LARRY_ATTACH_ACCEPT}
            multiple
            onChange={(event) => {
              const picked = snapshotFiles(event.currentTarget.files);
              event.currentTarget.value = "";
              if (picked.length) void attachFiles(picked);
            }}
          />
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="relative z-10 size-9 shrink-0"
            disabled={!enabled || locked || uploadingFiles || (pane.pendingAttachments ?? []).length >= LARRY_ATTACH_MAX_FILES}
            aria-label="Attach files"
            title="Attach PDF, text, or an image"
            onClick={() => fileInputRef.current?.click()}
          >
            {uploadingFiles ? <LoaderCircle className="size-4 animate-spin" /> : <Paperclip className="size-4" />}
          </Button>
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="relative z-10 size-9 shrink-0"
            disabled={!enabled || locked || busy || uploadingFiles}
            aria-label="Imagine"
            title="Imagine — generate an image from this prompt"
            onClick={() => void imagine()}
          >
            <Sparkles className="size-4" />
          </Button>
          {sttEnabled && !locked ? (
            <JuniorMicControls
              enabled={enabled && !uploadingFiles}
              locked={locked}
              registerAbort={voice.registerMicAbort}
              registerStsRearm={voice.registerStsRearm}
              onPhaseChange={voice.handleMicPhaseChange}
              onStsModeChange={voice.handleStsModeChange}
              onStsSubmit={submitVoiceTranscript}
              onSttDraft={applySttDraft}
              onSttEmptyHint={voice.showSttEmptyHint}
            />
          ) : null}
          {busy || aborting ? (
            <Button
              type="button"
              size="icon"
              variant="destructive"
              className="relative z-10 size-9 shrink-0"
              aria-label="Stop"
              title="Stop generating"
              onClick={() => stopGeneration()}
            >
              <Square className="size-3.5 fill-current" />
            </Button>
          ) : (
            <Button
              type="submit"
              size="icon"
              className="relative z-10 size-9 shrink-0"
              disabled={
                !enabled ||
                aborting ||
                voice.sttBusy ||
                (!draftNow().trim() && !(pane.pendingAttachments ?? []).length)
              }
              aria-label="Send"
            >
              <Send className="size-4" />
            </Button>
          )}
        </div>
        {voice.sttPhase === "listening" ? (
          <p className="text-[11px] text-muted-foreground" role="status">
            {voice.micMode === "stt" ? "STT" : "STS"} — {MIC_LIVE}
          </p>
        ) : voice.sttPhase === "transcribing" ? (
          <p className="text-[11px] text-muted-foreground" role="status">
            {voice.micMode === "stt" ? "STT" : "STS"} — {MIC_TRANSCRIBING}
          </p>
        ) : voice.sttEmptyHint ? (
          <p className="text-[11px] text-muted-foreground" role="status">
            {MIC_STT_EMPTY_HINT}
          </p>
        ) : voice.stsModeOn ? (
          <p className="text-[11px] text-muted-foreground" role="status">
            STS — conversation mode
          </p>
        ) : null}
        {(busy || aborting) && inFlightSpend ? (
          <p className="text-[11px] text-muted-foreground" data-junior-spend="" data-junior-route="">
            {inFlightSpend}
          </p>
        ) : null}
        {dragOver ? (
          <p className="text-[10px] text-muted-foreground">Drop files here — PDF, Word (.docx), or text up to 40 MB, or an image up to 10 MB.</p>
        ) : null}
        {process.env.NEXT_PUBLIC_BUILD_SHA ? (
          <p className="text-[10px] text-muted-foreground" title="Deployed build">
            Build {process.env.NEXT_PUBLIC_BUILD_SHA}
          </p>
        ) : null}
      </form>
    </div>
  );
}


