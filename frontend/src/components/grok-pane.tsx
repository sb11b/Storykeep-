"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Image as ImageIcon, LoaderCircle, Paperclip, Pencil, Save, Send, Sparkles, Square, X } from "lucide-react";
import { GrokRowMenu } from "@/components/grok-row-menu";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { useDictation } from "@/components/dictation";
import { DestinationSelect, FolderSelect } from "@/components/destination-controls";
import { JuniorMicButton, type JuniorMicPhase } from "@/components/junior-mic";
import { GrokChatMessage, type AddToNotesPayload } from "@/components/grok-chat-message";
import { CalendarProposalCard } from "@/components/calendar-overlay";
import { MailProposalCard } from "@/components/mail-overlay";
import { GrokListenBar, useGrokMessageListen } from "@/components/grok-message-listen";
import { logReplyText, readReplyText } from "@/lib/grok-reply-speech";
import { wordIndexFromSelection } from "@/lib/tts-words";
import { DEFAULT_PANE_NAME, defaultGrokPaneName, chatStatusLine, closeAssistantTurn, NO_REPLY_TOAST, normalizeTurnStatus, type ChatStatusKind, type ChatTurnStatus } from "@/lib/grok-pane-name";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { encryptMessageBody } from "@/lib/message-crypto";
import { destinationLabel, type CustomNoteShelf, type FilingDestination } from "@/lib/custom-note-shelves";
import { folderById } from "@/lib/folders";
import { filingFromDropdowns, loadLastFiling, saveLastFiling } from "@/lib/last-filing";
import {
  chatTimeoutToast,
  formatChatError,
  isOversizedPasteHttp,
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
  LARRY_IMAGE_ACCEPT,
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
import { DEFAULT_TTS_VOICE_ID, fallbackTtsVoices, resolveTtsVoiceId } from "@/lib/tts-defaults";
import { readStoredTtsSpeed, readStoredTtsVoice, TTS_SPEEDS, writeStoredTtsSpeed, writeStoredTtsVoice } from "@/lib/tts-preferences";
import { MIC_LIVE, MIC_TRANSCRIBING } from "@/lib/stt-ui";
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

function titleFromReply(reply: string, assistantName: string) {
  const fallback = `${assistantName} note`;
  const line = reply.trim().split("\n").find((item) => item.trim()) || fallback;
  return line.replace(/^#+\s*/, "").replace(/^["“]+|["”]+$/g, "").slice(0, 80) || fallback;
}

function noteMarkdown(reply: string, articleTitle: string | null, sourceRef: string | null, assistantName: string) {
  const heading = titleFromReply(reply, assistantName);
  const source = articleTitle || sourceRef;
  if (!source) return `# ${heading}\n\n${reply.trim()}`;
  return `# ${heading}\n\nAbout: ${source}${sourceRef ? `\nPath: ${sourceRef}` : ""}\n\n${reply.trim()}`;
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
  const imageInputRef = useRef<HTMLInputElement>(null);
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
  const [folders, setFolders] = useState<Folder[]>([]);
  const [voiceId, setVoiceId] = useState(() => readStoredTtsVoice(defaultTtsVoiceId));
  const [playbackSpeed, setPlaybackSpeed] = useState(() => readStoredTtsSpeed());
  const [listenTarget, setListenTarget] = useState<ListenTarget | null>(null);
  const [activeWord, setActiveWord] = useState<number | null>(null);
  const [uploadingFiles, setUploadingFiles] = useState(false);
  const [sttPhase, setSttPhase] = useState<JuniorMicPhase>("idle");
  const micAbortRef = useRef<(() => void) | null>(null);
  const sendRef = useRef<
    (opts?: {
      message?: string;
      fromStt?: boolean;
      keepDraft?: string;
      skipPasteSplit?: boolean;
      includeMode?: IncludeMode;
      includeHeading?: string | null;
      includeSelection?: string | null;
      includeOffset?: number;
    }) => Promise<void>
  >(async () => {});
  const sttBusy = sttPhase === "listening" || sttPhase === "transcribing";
  const [dragOver, setDragOver] = useState(false);
  const [streamStatus, setStreamStatus] = useState<ChatStatusKind | null>(null);
  const streamStatusRef = useRef<ChatStatusKind | null>(null);
  streamStatusRef.current = streamStatus;
  const [aborting, setAborting] = useState(false);
  const [inFlightSpend, setInFlightSpend] = useState<string | null>(null);
  const turnSpendRef = useRef({ model: "grok-4.6", reasoning: "low" });
  const [savingChat, setSavingChat] = useState(false);
  const [notePickerOpen, setNotePickerOpen] = useState(false);
  const [noteQuery, setNoteQuery] = useState("");
  const [noteChoices, setNoteChoices] = useState<Array<{ id: string; title: string }>>([]);
  const [loadingNotes, setLoadingNotes] = useState(false);
  const thinkingTimerRef = useRef<number | null>(null);
  const gotDeltaRef = useRef(false);
  const generatingRef = useRef(false);
  const pendingListenRef = useRef(false);
  const pendingFromHereRef = useRef<number | null>(null);
  const clickedWordRef = useRef<{ messageId: string; index: number } | null>(null);
  const listenTargetRef = useRef<ListenTarget | null>(null);
  const createInFlightRef = useRef<Promise<string> | null>(null);
  const createNonceRef = useRef<string | null>(pane.createNonce);
  createNonceRef.current = pane.createNonce;

  useEffect(() => {
    if (!pane.createNonce && !pane.conversationId) {
      createInFlightRef.current = null;
    }
  }, [pane.createNonce, pane.conversationId]);
  const bodyElementsRef = useRef<Map<string, HTMLElement>>(new Map());
  const messagesRef = useRef(pane.messages);
  listenTargetRef.current = listenTarget;
  messagesRef.current = pane.messages;
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
      if (mapped === "writing") gotDeltaRef.current = true;
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

  useEffect(() => {
    void api.folders().then(setFolders).catch(() => setFolders([]));
  }, []);

  useEffect(() => {
    if (!notePickerOpen) return;
    let cancelled = false;
    setLoadingNotes(true);
    void api
      .noteTitles(noteQuery, 20)
      .then((payload) => {
        if (!cancelled) setNoteChoices(payload.items || []);
      })
      .catch(() => {
        if (!cancelled) setNoteChoices([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingNotes(false);
      });
    return () => {
      cancelled = true;
    };
  }, [notePickerOpen, noteQuery]);

  useEffect(() => {
    if (!ttsVoices.length) return;
    let cancelled = false;
    void api
      .getPreferences()
      .then((prefs) => {
        if (cancelled) return;
        const saved = typeof prefs.tts_voice_id === "string" ? prefs.tts_voice_id : null;
        const local = readStoredTtsVoice(defaultTtsVoiceId);
        const next = resolveTtsVoiceId(ttsVoices, defaultTtsVoiceId, saved || local);
        setVoiceId(next);
        writeStoredTtsVoice(next);
      })
      .catch(() => {
        if (cancelled) return;
        const next = resolveTtsVoiceId(ttsVoices, defaultTtsVoiceId, readStoredTtsVoice(defaultTtsVoiceId));
        setVoiceId(next);
      });
    return () => {
      cancelled = true;
    };
  }, [defaultTtsVoiceId, ttsVoices]);

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
  const resolveListenScript = useCallback(() => {
    const target = listenTargetRef.current;
    if (!target) return "";
    if (target.script) return target.script;
    const resolved = readReplyText({
      trigger: target.trigger,
      body: bodyElementsRef.current.get(target.id) ?? null,
      markdown: messagesRef.current.find((item) => item.id === target.id)?.content ?? null,
    });
    logReplyText("resolve", resolved);
    return resolved.text;
  }, []);

  const listen = useGrokMessageListen({
    messageId: listenTarget?.id ?? "",
    resolveScript: resolveListenScript,
    voiceId,
    disabled: !listenTarget || !ttsEnabled || locked,
    onCue: setActiveWord,
    onPlayingChange: (active) => {
      if (active) {
        onStopArticleListen?.();
        onActivateListen(() => stopRef.current());
      } else {
        // Keep the target: clearing it here tore down the request mid-flight.
        onActivateListen(null);
        setActiveWord(null);
      }
    },
  });

  const listenApiRef = useRef(listen);
  listenApiRef.current = listen;
  stopRef.current = listen.stop;

  useEffect(() => {
    if (pendingListenRef.current && listenTarget) {
      pendingListenRef.current = false;
      const fromHere = pendingFromHereRef.current;
      pendingFromHereRef.current = null;
      if (fromHere != null) void listenApiRef.current.listenFromWord(fromHere);
      else listenApiRef.current.listen();
    }
  }, [listenTarget]);

  useEffect(() => {
    if (!panelOpen) listenApiRef.current.stop();
  }, [panelOpen]);

  const registerBody = useCallback((messageId: string, element: HTMLElement | null) => {
    if (element) bodyElementsRef.current.set(messageId, element);
    else bodyElementsRef.current.delete(messageId);
  }, []);

  /** Sticky bar with no active target reads the newest assistant reply. */
  function listenLatestReply() {
    if (listenTarget) {
      requestListen(listenTarget.id, listenTarget.trigger);
      return;
    }
    const latest = [...pane.messages]
      .reverse()
      .find((item) => item.role === "assistant" && item.content);
    if (!latest) {
      toast.error("Send a message first — there is no reply to read yet.");
      return;
    }
    requestListen(latest.id, null);
  }

  function requestListen(messageId: string, trigger: HTMLElement | null) {
    if (listen.isActive && listenTarget?.id !== messageId) {
      listen.stop();
    }
    if (listen.isActive && listenTarget?.id === messageId) {
      if (listen.phase === "playing") {
        listen.pause();
      } else {
        listen.listen();
      }
      return;
    }
    const resolved = readReplyText({
      trigger,
      body: bodyElementsRef.current.get(messageId) ?? null,
      markdown: pane.messages.find((item) => item.id === messageId)?.content ?? null,
    });
    logReplyText("click", resolved);
    if (!resolved.chars) {
      toast.error("That reply is still empty — nothing to read yet.");
      return;
    }
    pendingListenRef.current = true;
    setListenTarget({ id: messageId, trigger, script: resolved.text });
  }

  function readableAssistant(messageId?: string | null) {
    if (messageId) {
      const match = pane.messages.find((item) => item.id === messageId && item.role === "assistant" && item.content);
      if (match) return match;
    }
    if (listenTarget) {
      const match = pane.messages.find((item) => item.id === listenTarget.id && item.role === "assistant" && item.content);
      if (match) return match;
    }
    return [...pane.messages].reverse().find((item) => item.role === "assistant" && item.content) ?? null;
  }

  function listenFromHere() {
    const target = readableAssistant(clickedWordRef.current?.messageId);
    if (!target) {
      toast.error("Send a message first — there is no reply to read yet.");
      return;
    }
    const body = bodyElementsRef.current.get(target.id) ?? null;
    const word = wordIndexFromSelection(body) ?? (clickedWordRef.current?.messageId === target.id ? clickedWordRef.current.index : null);
    if (word == null || word < 0) {
      toast.error("Click or highlight a word in the reply first.");
      return;
    }
    const resolved = readReplyText({
      trigger: listenTarget?.id === target.id ? listenTarget.trigger : null,
      body,
      markdown: target.content,
    });
    logReplyText("from-here", resolved);
    if (!resolved.chars) {
      toast.error("That reply is still empty — nothing to read yet.");
      return;
    }
    if (listenTarget?.id === target.id && listen.isActive) {
      void listen.listenFromWord(word);
      return;
    }
    pendingFromHereRef.current = word;
    pendingListenRef.current = true;
    setListenTarget({ id: target.id, trigger: null, script: resolved.text });
  }

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

  async function runStream(options: {
    message: string;
    retry?: boolean;
    userLine?: ChatLine;
    assistantId: string;
    mediaIds?: string[];
    includeMode?: IncludeMode;
    includeHeading?: string | null;
    includeSelection?: string | null;
    includeOffset?: number;
    controller?: AbortController;
    turnId?: number;
  }) {
    const { message, retry = false, userLine, assistantId } = options;
    const turnId = options.turnId ?? turnIdRef.current;
    const controller = options.controller ?? new AbortController();
    if (turnId !== turnIdRef.current || controller.signal.aborted) return;
    abortRef.current = controller;
    abortingRef.current = false;
    setAborting(false);
    const posted = postedSpendForTurn(pane.modelChoice, pane.reasoningEffort, message);
    turnSpendRef.current = posted;
    setInFlightSpend(spendChipLabel(posted.model, posted.reasoning));
    onUpdate((current) => ({
      ...current,
      lastResolvedModel: posted.model,
      lastResolvedReasoning: posted.reasoning,
    }));

    setBusy(true);
    let streamFailed = false;
    let streamedText = "";
    let conversationId: string | null = conversationIdForRequest(pane.conversationId);
    try {
      conversationId = conversationIdForRequest(pane.conversationId);
      if (persist && !retry) {
        conversationId = await ensureOwnedConversation();
      }
      if (persist && !conversationId) {
        throw new ApiError(422, INVALID_CHAT_TOAST);
      }
      const threadRows = pane.messages.filter((item) => item.id !== assistantId && item.content?.trim());
      const windowedRows = threadRows.slice(-GROK_CONTEXT_THREAD_WINDOW);
      const historyOverride = messageCryptoEnabled
        ? [
            ...windowedRows.map((item) => ({ role: item.role, content: item.content || "" })),
            ...(retry || !userLine ? [] : [{ role: "user" as const, content: userLine.content || message }]),
          ].slice(-GROK_CONTEXT_THREAD_WINDOW)
        : undefined;
      const clientTitle =
        messageCryptoEnabled && !retry && !pane.conversationTitle && userLine?.content
          ? userLine.content.trim().split("\n", 1)[0]?.slice(0, 80)
          : undefined;
      if (messageCryptoEnabled && conversationId && userLine && !retry) {
        const blob = await encryptMessageBody(userLine.content || message);
        const saved = await api.postEncryptedMessage(conversationId, {
          role: "user",
          iv: blob.iv,
          ct: blob.ct,
          id: userLine.id,
          title: clientTitle,
          media_ids: options.mediaIds,
        });
        if (saved.id !== userLine.id) {
          onUpdate((current) => ({
            ...current,
            messages: current.messages.map((item) =>
              item.id === userLine.id ? { ...item, id: saved.id } : item,
            ),
          }));
        }
      }
      await api.streamChat(
        {
          message,
          retry,
          conversation_id: conversationId,
          model: pane.modelChoice,
          reasoning_effort: pane.modelChoice === "auto" ? "auto" : pane.reasoningEffort,
          article_id: articleId,
          include_article: Boolean(pane.includeArticle && articleId),
          include_note_id: pane.includeNoteId || undefined,
          working_note_id: pane.workingNoteId || undefined,
          include_mode: options.includeMode || pane.includeMode,
          include_selection: options.includeSelection || undefined,
          include_heading: options.includeHeading || pane.includeHeading || undefined,
          include_offset: options.includeOffset ?? pane.includeOffset ?? 0,
          recap_question: pane.recapQuestion,
          media_ids: retry ? undefined : options.mediaIds,
          history_override: historyOverride,
          client_title: clientTitle,
        },
        (delta) => {
          if (turnId !== turnIdRef.current) return;
          if ((delta || "").trim()) gotDeltaRef.current = true;
          const generating = generatingRef.current;
          if (!generating) markWriting();
          onUpdate((current) => ({
            ...current,
            streamStatus: generating ? "generating" : "writing",
            messages: current.messages.map((item) => {
              if (item.id !== assistantId) return item;
              const nextContent = MEDIA_MARKDOWN.test(delta) ? delta : item.content + delta;
              streamedText = nextContent;
              return {
                ...item,
                waiting: true,
                turnStatus: generating ? "writing" : "writing",
                content: nextContent,
                failed: false,
                error: null,
              };
            }),
          }));
        },
        (meta) => {
          if (turnId !== turnIdRef.current) return;
          if (
            meta.stream_status === "working" ||
            meta.stream_status === "queued" ||
            meta.stream_status === "thinking" ||
            meta.stream_status === "writing" ||
            meta.stream_status === "generating" ||
            meta.stream_status === "searching"
          ) {
            applyStreamStatus(meta.stream_status);
            const turn = normalizeTurnStatus(meta.stream_status);
            if (turn && turn !== "done") {
              onUpdate((current) => ({
                ...current,
                messages: current.messages.map((item) =>
                  item.id === assistantId && !item.content
                    ? { ...item, waiting: true, turnStatus: turn, failed: false }
                    : item,
                ),
              }));
            }
          }
          if (meta.toast) {
            if (meta.toast_kind === "error") toast.error(meta.toast);
            else toast.message(meta.toast);
          }
          onUpdate((current) => {
            let next = current;
            if (meta.conversation_id && meta.conversation_id !== current.conversationId) {
              const firstUser = current.messages.find((item) => item.role === "user")?.content || "";
              next = {
                ...next,
                conversationId: meta.conversation_id,
                conversationTitle: current.conversationTitle || firstUser.trim().split("\n")[0] || null,
              };
            }
            if (meta.user_message_id && userLine) {
              next = {
                ...next,
                messages: next.messages.map((item) =>
                  item.id === userLine.id ? { ...item, id: meta.user_message_id! } : item,
                ),
              };
            }
            if (meta.assistant_message_id) {
              next = {
                ...next,
                messages: next.messages.map((item) =>
                  item.id === assistantId
                    ? {
                        ...item,
                        id: meta.assistant_message_id!,
                        failed: meta.partial ? item.failed : item.failed,
                        error: meta.partial ? item.error : item.error,
                      }
                    : item,
                ),
              };
            }
            if (meta.model) {
              next = { ...next, lastResolvedModel: meta.model };
            }
            if (meta.reasoning_effort) {
              next = { ...next, lastResolvedReasoning: meta.reasoning_effort };
            }
            if (meta.include_chip) {
              next = {
                ...next,
                includeOffset: meta.include_next_offset ?? next.includeOffset,
                includeHeading: meta.include_next_heading ?? next.includeHeading,
                includeMode: meta.include_has_more
                  ? meta.include_next_heading
                    ? "heading"
                    : "chunk"
                  : next.includeMode,
                messages: next.messages.map((item) =>
                  item.id === assistantId || item.id === userLine?.id
                    ? {
                        ...item,
                        includeChip: meta.include_chip,
                        includeHasMore: item.role === "assistant" ? Boolean(meta.include_has_more) : item.includeHasMore,
                        includeNextOffset: meta.include_next_offset ?? null,
                        includeNextHeading: meta.include_next_heading ?? null,
                      }
                    : item,
                ),
              };
            }
            if (meta.calendar_proposal) {
              next = {
                ...next,
                messages: next.messages.map((item) =>
                  item.id === assistantId || item.id === meta.assistant_message_id
                    ? {
                        ...item,
                        calendarProposal: { ...meta.calendar_proposal!, status: "pending" },
                      }
                    : item,
                ),
              };
            }
            if (meta.mail_proposal) {
              next = {
                ...next,
                messages: next.messages.map((item) =>
                  item.id === assistantId || item.id === meta.assistant_message_id
                    ? {
                        ...item,
                        mailProposal: { ...meta.mail_proposal!, status: "pending" },
                      }
                    : item,
                ),
              };
            }
            if (meta.media_id) {
              const targetId = meta.assistant_message_id || assistantId;
              next = {
                ...next,
                messages: next.messages.map((item) =>
                  item.id === targetId || item.id === assistantId
                    ? {
                        ...item,
                        files: [
                          ...(item.files || []).filter((file) => file.media_id !== meta.media_id),
                          {
                            media_id: meta.media_id!,
                            filename: "generated image",
                            content_type: "image/png",
                            kind: "image" as const,
                            url: `/api/v1/media/${meta.media_id}`,
                          },
                        ],
                      }
                    : item,
                ),
              };
            }
            if (meta.model || meta.reasoning_effort) {
              const model = meta.model || turnSpendRef.current.model;
              const reasoning = meta.reasoning_effort || turnSpendRef.current.reasoning;
              turnSpendRef.current = { model, reasoning };
              const spend = spendChipLabel(model, reasoning);
              setInFlightSpend(spend);
              const targetId = meta.assistant_message_id || assistantId;
              next = {
                ...next,
                messages: next.messages.map((item) =>
                  item.id === targetId || item.id === assistantId ? { ...item, routeLabel: spend } : item,
                ),
              };
            }
            return next;
          });
          if (meta.conversation_id || meta.assistant_message_id) onHistoryChanged?.();
        },
        controller.signal,
        () => {
          if (turnId !== turnIdRef.current) return;
          if (!gotDeltaRef.current) applyStreamStatus("thinking");
        },
      );
    } catch (error) {
      if (turnId !== turnIdRef.current) return;
      streamFailed = true;
      const aborted = controller.signal.aborted && !(error instanceof ApiError);
      if (aborted) {
        failOpenTurn(assistantId, true);
        toast.error(NO_REPLY_TOAST);
        return;
      }
      const status = error instanceof ApiError ? error.status : 502;
      const detail = error instanceof ApiError ? error.message : `${label} did not reply`;
      const createToast = error instanceof ApiError ? chatCreateErrorToast(status, detail) : null;
      const formatted = createToast
        ? createToast
        : detail.startsWith("Chat failed (HTTP")
          ? withAssistantName(detail, label)
          : formatChatError(status, detail, label);
      const oversizedPaste = isOversizedPasteHttp(status, detail);
      const turnText = userLine?.content || message;
      if (oversizedPaste && turnText.length >= PASTE_FIRST_CHUNK_CHARS) {
        offerPasteSplit(turnText);
      }
      const imageFail = generatingRef.current || /did not return an image|could not generate that image/i.test(detail);
      const shortImage = readableXaiToast(detail);
      const capDetail = /over the cap|too long|Recent messages are too long/i.test(detail) ? detail : null;
      const timeoutDetail = chatTimeoutToast(status, detail);
      const emptyDetail = /returned no text|xai silent/i.test(detail) ? readableXaiToast(detail) : null;
      const toastText = imageFail
        ? (shortImage.length > 180 ? "Could not generate that image." : shortImage)
        : capDetail
          ? capDetail
          : emptyDetail
            ? emptyDetail
            : timeoutDetail && status === 504
              ? timeoutDetail
              : oversizedPaste && turnText.length >= PASTE_FIRST_CHUNK_CHARS
                ? pasteSplitToast(turnText.length)
                : status === 413 || status === 400
                  ? detail
                  : status === 502
                    ? readableXaiToast(detail)
                    : NO_REPLY_TOAST;
      onUpdate((current) => ({
        ...current,
        streamStatus: "error",
        draft: oversizedPaste && (userLine?.content || message) ? userLine?.content || message : current.draft,
        messages: current.messages.map((item) => {
          const target = item.role === "assistant" && (item.waiting || item.id === assistantId);
          if (!target) return item;
          const kept = (item.content || "").trim();
          const wipePlaceholder =
            !hasMediaImage(item.content) &&
            !/\/api\/v1\/media\//.test(item.content) &&
            /Generating the image|Here's the image|implemented and passing/i.test(item.content);
          const empty = wipePlaceholder || !kept;
          return {
            ...item,
            waiting: false,
            turnStatus: "error" as const,
            failed: true,
            error: empty
              ? imageFail
                ? shortImage || "Could not generate that image."
                : NO_REPLY_TOAST
              : formatted,
            content: wipePlaceholder ? "" : item.content,
          };
        }),
      }));
      applyStreamStatus("error");
      if (!oversizedPaste) {
        toast.error(toastText);
      }
    } finally {
      if (turnId !== turnIdRef.current) return;
      if (abortRef.current === controller) abortRef.current = null;
      abortingRef.current = false;
      setAborting(false);
      setBusy(false);
      if (streamFailed) return;
      const hasReply =
        gotDeltaRef.current ||
        Boolean(streamedText.trim()) ||
        hasMediaImage(streamedText) ||
        /\/api\/v1\/media\//.test(streamedText);
      if (hasReply) {
        clearStreamStatus();
        onUpdate((current) => ({
          ...current,
          streamStatus: null,
          messages: current.messages.map((item) =>
            item.id === assistantId || item.waiting
              ? { ...item, waiting: false, turnStatus: "done" as const, failed: false, error: null }
              : item,
          ),
        }));
        if (messageCryptoEnabled && conversationId && streamedText.trim()) {
          try {
            const blob = await encryptMessageBody(streamedText);
            await api.postEncryptedMessage(conversationId, {
              role: "assistant",
              iv: blob.iv,
              ct: blob.ct,
              id: assistantId,
            });
          } catch (error) {
            toastActionError(error, "save encrypted reply", "Could not save the encrypted reply.");
          }
        }
        return;
      }
      failOpenTurn(assistantId, false);
      toast.error(NO_REPLY_TOAST);
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

  function contextInput(draft: string, extraMessages: ChatLine[] = pane.messages) {
    const noteBody =
      pane.includeNoteId && articleId && pane.includeNoteId === articleId ? articleBody : null;
    const slice = plannedIncludeSlice();
    const workingSlice = plannedWorkingSlice();
    return {
      messages: extraMessages,
      draft,
      includeArticle: Boolean(pane.includeArticle && articleId),
      articleBody,
      includeNote: Boolean(pane.includeNoteId),
      noteBody,
      includeSliceChars: slice?.chars,
      workingNoteSliceChars: workingSlice?.chars,
      pendingExtracts: (pane.pendingAttachments ?? []).map((item) => item.extract_text),
    };
  }

  function contextTooLarge(draft: string, extraMessages: ChatLine[] = pane.messages) {
    return chatContextOverCap(contextInput(draft, extraMessages));
  }

  function pasteChunkSize() {
    const used = estimateChatContextChars(contextInput(""));
    const budget = GROK_CONTEXT_CHAR_CAP - used;
    return Math.min(PASTE_FIRST_CHUNK_CHARS, Math.max(1, budget));
  }

  function offerPasteSplit(draft: string) {
    const source = draft;
    const n = source.length;
    toast.custom(
      (id) => (
        <div className="flex w-[min(100%,22rem)] flex-col gap-2 rounded-lg border bg-background p-3 text-sm shadow-md">
          <p>{pasteSplitToast(n)}</p>
          <div className="flex flex-col gap-1">
            <Button
              type="button"
              size="sm"
              className="h-8 justify-start"
              onClick={() => {
                toast.dismiss(id);
                const { first, remainder } = splitPasteChunk(source, pasteChunkSize());
                void send({ message: first, keepDraft: remainder, skipPasteSplit: true });
              }}
            >
              Send first chunk
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8 justify-start"
              onClick={() => {
                const selected = textareaSelection(draftRef.current) || readerCtx.selection;
                if (!selected.trim()) {
                  toast.error("Highlight text in the box, then Include selection.");
                  return;
                }
                toast.dismiss(id);
                void send({
                  message: selected,
                  keepDraft: source,
                  skipPasteSplit: selected.length <= PASTE_FIRST_CHUNK_CHARS,
                });
              }}
            >
              Include selection
            </Button>
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-8 justify-start"
              onClick={() => {
                toast.dismiss(id);
                const { first, remainder } = splitPasteChunk(source, pasteChunkSize());
                let parked = false;
                if (remainder && onOpenRemainderChat) {
                  parked = Boolean(onOpenRemainderChat(remainder));
                }
                if (remainder && !parked) {
                  toast.message("Remainder stayed in this box — Junior is full.");
                }
                void send({
                  message: first,
                  keepDraft: remainder && !parked ? remainder : "",
                  skipPasteSplit: true,
                });
              }}
            >
              New chat with remainder
            </Button>
          </div>
        </div>
      ),
      { duration: 30_000 },
    );
  }

  async function send(opts?: {
    message?: string;
    fromStt?: boolean;
    keepDraft?: string;
    skipPasteSplit?: boolean;
    includeMode?: IncludeMode;
    includeHeading?: string | null;
    includeSelection?: string | null;
    includeOffset?: number;
  }) {
    if (!opts?.fromStt) {
      dictation?.abort();
      micAbortRef.current?.();
    }
    const content = (opts?.message ?? draftNow()).trim();
    const pending = pane.pendingAttachments ?? [];
    if (pending.some((item) => !item.id)) {
      toast.error("Wait for the file to finish uploading.");
      return;
    }
    const files = pending.filter((item) => item.id);
    if ((!content && !files.length) || busy || aborting || abortingRef.current || !enabled || inFlightRef.current) {
      if (opts?.fromStt && content) {
        toast.error("Could not send voice message — try again or tap Send.");
      }
      return;
    }
    if (pane.includeArticle && articleId) {
      const mode = opts?.includeMode || pane.includeMode;
      if (mode === "selection" && !(opts?.includeSelection || readerCtx.selection)) {
        toast.error("Highlight text in the reader, then Include selection.");
        return;
      }
      if (mode === "heading" && !(opts?.includeHeading || pane.includeHeading)) {
        toast.error("Pick a heading from this note.");
        return;
      }
    }
    if (contextTooLarge(content)) {
      const raw = opts?.message ?? draftNow();
      const capToast = threadContextToast(contextInput(content));
      if (!opts?.skipPasteSplit && raw.length >= PASTE_FIRST_CHUNK_CHARS) {
        offerPasteSplit(raw);
        return;
      }
      toast.error(capToast);
      return;
    }
    inFlightRef.current = true;
    const turnId = ++turnIdRef.current;
    const controller = new AbortController();
    abortRef.current = controller;
    abortingRef.current = false;
    setAborting(false);
    setBusy(true);
    try {
    const imageIds = thisTurnImageMediaIds(files);
    const intent = imageToolIntent(content, imageIds.length > 0);
    const wantsImage = intent === "edit" || intent === "generate";
    let includeMode = opts?.includeMode || pane.includeMode;
    let includeHeading = opts?.includeHeading ?? pane.includeHeading;
    const includeSelection = opts?.includeSelection || (includeMode === "selection" ? readerCtx.selection : undefined);
    const includeOffset = opts?.includeOffset ?? pane.includeOffset ?? 0;
    if (pane.workingNoteId && (includeMode === "auto" || !includeMode) && !includeHeading) {
      const guessed = headingFromInstruction(
        content,
        pane.workingNoteId === articleId ? articleBody || "" : "",
      );
      if (guessed) {
        includeMode = "heading";
        includeHeading = guessed;
      }
    }
    const workingBody = pane.workingNoteId === articleId ? articleBody || "" : "";
    const previewSlice = pane.workingNoteId
      ? workingBody
        ? resolveIncludeSlice({
            body: workingBody,
            mode:
              includeMode === "auto" && articleNeedsIncludeSlice(workingBody, WORKING_NOTE_CHAR_CAP)
                ? "chunk"
                : includeMode,
            heading: includeHeading,
            offset: includeOffset,
            title: pane.workingNoteTitle || articleTitle,
            cap: WORKING_NOTE_CHAR_CAP,
            hardMax: WORKING_NOTE_CHAR_CAP,
          })
        : null
      : pane.includeArticle && articleId
        ? resolveIncludeSlice({
            body: articleBody || "",
            mode: includeMode === "auto" && articleNeedsIncludeSlice(articleBody) ? "chunk" : includeMode,
            selection: includeSelection,
            heading: includeHeading,
            offset: includeOffset,
            title: articleTitle,
          })
        : null;
    const userLine: ChatLine = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      files: files.map(pendingToMessageFile),
      includeChip: previewSlice?.chip,
      includeMode,
      includeHeading,
      includeOffset,
    };
    const assistantId = crypto.randomUUID();
    onUpdate((current) => ({
      ...current,
      draft: opts?.keepDraft ?? "",
      pendingAttachments: [],
      streamStatus: wantsImage ? "generating" : "queued",
      messages: [
        ...current.messages,
        userLine,
        { id: assistantId, role: "assistant", content: "", waiting: true, turnStatus: wantsImage ? "writing" : "queued" },
      ],
    }));
    setStreamStatus(wantsImage ? "generating" : "queued");
    await runStream({
      message: content || (files[0] ? `Please look at ${files.map((item) => item.name).join(", ")}.` : ""),
      userLine,
      assistantId,
      mediaIds: files.map((item) => item.id),
      includeMode,
      includeHeading,
      includeSelection,
      includeOffset,
      controller,
      turnId,
    });
    } finally {
      if (turnId === turnIdRef.current) inFlightRef.current = false;
    }
  }

  sendRef.current = send;

  const submitVoiceTranscript = useCallback(
    (transcript: string) => {
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
      }
      void sendRef.current({ message, fromStt: true });
    },
    [onUpdate],
  );

  async function runImagineFromChat(options: {
    prompt: string;
    mediaIds: string[];
    userLine: ChatLine;
    assistantId: string;
  }) {
    const { prompt, mediaIds, userLine, assistantId } = options;
    const controller = new AbortController();
    abortRef.current = controller;
    abortingRef.current = false;
    setAborting(false);
    setBusy(true);
    applyStreamStatus("generating");
    const routeLabel = spendChipLabel("grok-4.6", "low");
    setInFlightSpend(routeLabel);
    try {
      const result = await api.chatImagine(
        {
          prompt,
          conversation_id: pane.conversationId,
          media_ids: mediaIds.length ? mediaIds : undefined,
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
        conversationId: result.conversation_id || current.conversationId,
        lastResolvedModel: "grok-4.6",
        lastResolvedReasoning: "low",
        streamStatus: null,
        messages: current.messages.map((item) => {
          if (item.id === userLine.id) {
            return {
              id: result.user_message.id,
              role: "user" as const,
              content: result.user_message.content || "",
              files: result.user_message.files,
            };
          }
          if (item.id === assistantId) {
            return {
              id: result.assistant_message.id,
              role: "assistant" as const,
              content: result.assistant_message.content || "",
              files: result.assistant_message.files,
              waiting: false,
              failed: false,
              error: null,
              routeLabel,
            };
          }
          return item;
        }),
      }));
      onHistoryChanged?.();
    } catch (error) {
      if (controller.signal.aborted) {
        onUpdate((current) => ({
          ...current,
          streamStatus: null,
          messages: current.messages.map((item) =>
            item.id === assistantId ? { ...item, waiting: false } : item,
          ),
        }));
        return;
      }
      const status = error instanceof ApiError ? error.status : 502;
      const detail = error instanceof ApiError ? error.message : "Could not generate that image.";
      const formatted = formatChatError(status, detail, label);
      onUpdate((current) => ({
        ...current,
        streamStatus: null,
        messages: current.messages.map((item) =>
          item.id === assistantId
            ? { ...item, waiting: false, failed: true, error: formatted, content: "" }
            : item,
        ),
      }));
      toast.error("Could not generate that image.");
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      abortingRef.current = false;
      setAborting(false);
      setBusy(false);
      clearStreamStatus();
    }
  }

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

  async function retryAssistant(assistantId: string) {
    if (busy || aborting || abortingRef.current || !enabled || inFlightRef.current) return;
    if (!pane.conversationId) {
      toast.error("That thread is not ready to retry yet.");
      return;
    }
    const messages = pane.messages;
    const assistantIndex = messages.findIndex((item) => item.id === assistantId);
    if (assistantIndex < 1) return;
    const userLine = messages[assistantIndex - 1];
    if (!userLine || userLine.role !== "user") return;
    if (contextTooLarge("")) {
      toast.error(threadContextToast(contextInput("")));
      return;
    }
    inFlightRef.current = true;
    const turnId = ++turnIdRef.current;
    const controller = new AbortController();
    abortRef.current = controller;
    abortingRef.current = false;
    setAborting(false);
    setBusy(true);
    try {
    const retryImages = thisTurnImageMediaIds(userLine.files);
    const retryIntent = imageToolIntent(userLine.content, retryImages.length > 0);
    const retryWantsImage = retryIntent === "generate" || (retryIntent === "edit" && retryImages.length > 0);
    onUpdate((current) => ({
      ...current,
      streamStatus: retryWantsImage ? "generating" : "queued",
      messages: current.messages.map((item) =>
        item.id === assistantId
          ? { ...item, content: "", failed: false, error: null, waiting: true, turnStatus: retryWantsImage ? "writing" : "queued" }
          : item,
      ),
    }));
    setStreamStatus(retryWantsImage ? "generating" : "queued");
    await runStream({
      message: userLine.content,
      retry: true,
      userLine,
      assistantId,
      controller,
      turnId,
    });
    } finally {
      if (turnId === turnIdRef.current) inFlightRef.current = false;
    }
  }

  async function runSnippet(messageId: string, code: string) {
    const snippet = code.trim();
    if (!snippet) {
      toast.error("That code fence is empty.");
      return;
    }
    setBusy(true);
    try {
      const result = await api.runChatSnippet(messageId, snippet);
      onUpdate((current) => {
        const extra: ChatLine[] = [
          { id: result.user_message.id, role: "user", content: result.user_message.content || "" },
          {
            id: result.assistant_message.id,
            role: "assistant",
            content: result.assistant_message.content || "",
            routeLabel: spendChipLabel(current.lastResolvedModel, "low"),
          },
        ];
        const merged = [...current.messages];
        for (const line of extra) {
          if (!merged.some((row) => row.id === line.id)) merged.push(line);
        }
        return { ...current, conversationId: result.conversation_id || current.conversationId, messages: merged };
      });
      onHistoryChanged?.();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not run that snippet.");
    } finally {
      setBusy(false);
    }
  }

  async function addToNotes(payload: AddToNotesPayload, assistantId?: string) {
    const body = payload.content.trim();
    if (!body) return;
    const filing = filingFromDropdowns(payload.dest, payload.folderId, folders);
    const dest = filing.dest;
    const folderId = filing.folderId;
    saveLastFiling(dest, folderId);
    patch({ noteDest: dest, noteFolderId: folderId });
    const fromUser =
      assistantId != null
        ? (() => {
            const index = pane.messages.findIndex((item) => item.id === assistantId);
            const prior = index > 0 ? pane.messages[index - 1] : null;
            return prior?.role === "user" ? prior.files || [] : [];
          })()
        : [];
    const extra = attachmentMarkdown(fromUser);
    try {
      const markdown = extra
        ? `${noteMarkdown(body, articleTitle, sourceRef || null, label)}\n\n${extra}`
        : noteMarkdown(body, articleTitle, sourceRef || null, label);
      const article = await api.composeVaultNote(
        titleFromReply(body, label),
        markdown,
        ["grok"],
        dest,
        payload.isCorrection,
        folderId,
      );
      const filedDest = (article.destination as FilingDestination) || dest;
      const filedFolder = article.folder_id ?? folderId;
      saveLastFiling(filedDest, filedFolder);
      patch({ noteDest: filedDest, noteFolderId: filedFolder, savedNoteId: article.id });
      const folderName = folderById(folders, filedFolder)?.name;
      toast.success(
        folderName
          ? `Saved to StoryKeep/${destinationLabel(filedDest, customShelves)}/${folderName}.`
          : `Saved to StoryKeep/${destinationLabel(filedDest, customShelves)}.`,
      );
      await onSavedNote(article.id, filedDest, filedFolder);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not save that note");
    }
  }

  async function applyToWorkingNote(content: string, assistantId?: string) {
    const noteId = pane.workingNoteId;
    if (!noteId) return;
    const index = assistantId ? pane.messages.findIndex((item) => item.id === assistantId) : -1;
    const prior = index > 0 ? pane.messages[index - 1] : null;
    const save = async (confirmShort = false) => {
      try {
        const next = await api.applyJuniorReply(noteId, {
          markdown: content,
          confirm_short: confirmShort,
          mode: prior?.includeMode || pane.includeMode,
          heading: prior?.includeHeading || pane.includeHeading,
          offset: prior?.includeOffset ?? pane.includeOffset,
        });
        patch({ savedNoteId: next.id });
        toast.success("Applied to the note. Previous save is in History.");
        await onSavedNote(next.id, (next.destination as FilingDestination) || pane.noteDest, next.folder_id);
      } catch (error) {
        if (
          !confirmShort &&
          error instanceof ApiError &&
          error.status === 409 &&
          isNoteShrinkMessage(error.message)
        ) {
          if (window.confirm(error.message)) await save(true);
          return;
        }
        toast.error(error instanceof ApiError ? error.message : "Could not apply that reply");
      }
    };
    await save(false);
  }

  async function saveChat() {
    if (savingChat) return;
    const filing = filingFromDropdowns(pane.noteDest, pane.noteFolderId, folders);
    const dest = filing.dest;
    const folderId = filing.folderId;
    if (!dest) {
      toast.error("Pick a shelf before saving this chat.");
      document.getElementById(shelfSelectId)?.focus();
      return;
    }
    saveLastFiling(dest, folderId);
    patch({ noteDest: dest, noteFolderId: folderId });
    const turns = saveableThreadTurns(pane.messages);
    if (!turns.length) {
      toast.error("Nothing to save — this thread is empty.");
      return;
    }
    const title = threadNoteTitle({
      conversationTitle: pane.conversationTitle,
      firstUserLine: turns.find((item) => item.role === "user")?.content,
    });
    const markdown = threadNoteMarkdown(turns, { title, userName: "Steve", assistantName: "Junior" });
    setSavingChat(true);
    try {
      let article: Awaited<ReturnType<typeof api.composeVaultNote>> | null = null;
      let updated = false;
      if (pane.savedNoteId) {
        try {
          article = await api.updateComposedNote(
            pane.savedNoteId,
            title,
            markdown,
            dest,
            false,
            folderId,
          );
          updated = true;
        } catch (error) {
          if (!(error instanceof ApiError && error.status === 404)) {
            throw error;
          }
        }
      }
      if (!article) {
        article = await api.composeVaultNote(title, markdown, ["grok"], dest, false, folderId);
      }
      const filedDest = (article.destination as FilingDestination) || dest;
      const filedFolder = article.folder_id ?? folderId;
      saveLastFiling(filedDest, filedFolder);
      patch({ savedNoteId: article.id, conversationTitle: title, noteDest: filedDest, noteFolderId: filedFolder });
      if (pane.conversationId && persist) {
        try {
          await api.patchChatConversation(pane.conversationId, { saved_note_id: article.id });
        } catch {
          /* note is saved; linking it to the thread is best-effort */
        }
      }
      const folderName = folderById(folders, filedFolder)?.name;
      const where = folderName
        ? `${destinationLabel(filedDest, customShelves)} / ${folderName}`
        : destinationLabel(filedDest, customShelves);
      toast.success(updated ? `Updated “${title}” on ${where}.` : `Saved “${title}” to ${where}.`);
      await onSavedNote(article.id, filedDest, filedFolder);
    } catch (error) {
      toastErrorFromUnknown(error, "Could not save this chat");
    } finally {
      setSavingChat(false);
    }
  }

  function patch(partial: Partial<GrokPaneState>) {
    onUpdate((current) => ({ ...current, ...partial }));
  }

  async function setModelChoice(next: string) {
    const reasoning = next === "auto" ? "auto" : pane.reasoningEffort === "auto" ? "low" : pane.reasoningEffort;
    patch({ modelChoice: next, reasoningEffort: next === "auto" ? pane.reasoningEffort : reasoning });
    if (!pane.conversationId || !persist) return;
    try {
      const updated = await api.patchChatConversation(pane.conversationId, {
        model: next,
        reasoning: next === "auto" ? "auto" : reasoning,
      });
      patch({
        modelChoice: updated.model,
        lastResolvedModel: updated.last_model ?? pane.lastResolvedModel,
        reasoningEffort:
          updated.model === "auto"
            ? pane.reasoningEffort
            : isGrokReasoningEffort(updated.reasoning)
              ? updated.reasoning
              : reasoning,
        lastResolvedReasoning: updated.last_reasoning ?? pane.lastResolvedReasoning,
      });
      onHistoryChanged?.();
    } catch {
      /* ignore */
    }
  }

  async function setReasoningEffort(next: string) {
    patch({ reasoningEffort: next });
    if (pane.modelChoice === "auto" || !pane.conversationId || !persist) return;
    try {
      const updated = await api.patchChatConversation(pane.conversationId, { reasoning: next });
      patch({
        reasoningEffort: isGrokReasoningEffort(updated.reasoning) ? updated.reasoning : next,
        lastResolvedReasoning: updated.last_reasoning ?? pane.lastResolvedReasoning,
      });
      onHistoryChanged?.();
    } catch {
      /* ignore */
    }
  }

  async function setRecapQuestion(next: boolean) {
    patch({ recapQuestion: next });
    if (!pane.conversationId || !persist) return;
    try {
      await api.patchChatConversation(pane.conversationId, { recap_question: next });
    } catch {
      /* ignore */
    }
  }

  async function createNoteFolder(shelf: FilingDestination = pane.noteDest) {
    const name = window.prompt(`New folder on ${destinationLabel(shelf, customShelves)}`);
    if (!name?.trim()) return;
    try {
      const row = await api.createFolder(shelf, name.trim());
      setFolders((current) => [...current, row]);
      patch({ noteDest: shelf, noteFolderId: row.id });
      saveLastFiling(shelf, row.id);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not create folder");
    }
  }

  function handleNoteDestChange(next: FilingDestination | "") {
    if (!next) return;
    patch({ noteDest: next, noteFolderId: null });
    saveLastFiling(next, null);
  }

  function handleVoiceChange(next: string) {
    if (listen.isActive) {
      listenApiRef.current.stop();
    }
    setVoiceId(next);
    writeStoredTtsVoice(next);
    void api.updatePreferences({ tts_voice_id: next }).catch(() => {
      /* ignore */
    });
  }

  function handleSpeedChange(next: number) {
    setPlaybackSpeed(next);
    writeStoredTtsSpeed(next);
    listen.changeSpeed(next);
  }

  const modelOptions = ["auto", ...chatModels.filter((item, index, all) => all.indexOf(item) === index)];
  const voiceOptions = ttsVoices.length ? ttsVoices : fallbackTtsVoices();
  const hasReadableReply = pane.messages.some((item) => item.role === "assistant" && Boolean(item.content));
  const showStickyPlayer = ttsEnabled && !locked && (listen.isActive || hasReadableReply);
  const visibleStatus = pane.streamStatus ?? streamStatus;
  const lastAssistantId = [...pane.messages].reverse().find((item) => item.role === "assistant")?.id ?? null;
  const shelfSelectId = `junior-shelf-${pane.id}`;
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
                value={voiceId}
                onChange={(event) => handleVoiceChange(event.target.value)}
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
                value={playbackSpeed}
                onChange={(event) => handleSpeedChange(Number(event.target.value))}
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
          disabled={!canSaveChat || savingChat}
          aria-label="Save chat"
          title={canSaveChat ? "Save this whole thread as a StoryKeep note" : "Nothing to save"}
          onClick={() => void saveChat()}
        >
          <Save className="size-3.5" />
          {savingChat ? "Saving…" : "Save chat"}
        </Button>
      </div>

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
            phase={listen.phase}
            disabled={!ttsEnabled || locked}
            speed={listen.speed}
            voiceId={voiceId}
            voices={voiceOptions}
            onListen={listenLatestReply}
            onFromHere={listenFromHere}
            onPause={listen.pause}
            onStop={listen.stop}
            onSpeedChange={handleSpeedChange}
            onVoiceChange={handleVoiceChange}
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
                listening={listenTarget?.id === item.id && listen.isActive}
                activeWord={listenTarget?.id === item.id ? activeWord : null}
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
                onRegisterBody={registerBody}
                onListen={requestListen}
                onTtsWordPick={(messageId, index) => {
                  clickedWordRef.current = { messageId, index };
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
                checked={Boolean(pane.includeNoteId) || notePickerOpen}
                onChange={(event) => {
                  if (event.target.checked) {
                    setNotePickerOpen(true);
                    return;
                  }
                  setNotePickerOpen(false);
                  patch({ includeNoteId: null, includeNoteTitle: null });
                }}
              />
              Include note…
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
                    setNotePickerOpen(false);
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
          {notePickerOpen ? (
            <div className="rounded-md border bg-background p-1.5">
              <Input
                value={noteQuery}
                onChange={(event) => setNoteQuery(event.target.value)}
                placeholder="Search notes…"
                className="h-7 text-[12px]"
                aria-label="Search notes to include"
              />
              <ul className="mt-1 max-h-32 overflow-y-auto">
                {loadingNotes ? (
                  <li className="px-1 py-1 text-[11px] text-muted-foreground">Loading…</li>
                ) : noteChoices.length ? (
                  noteChoices.map((note) => (
                    <li key={note.id}>
                      <button
                        type="button"
                        className="w-full truncate rounded px-1 py-0.5 text-left text-[12px] hover:bg-muted"
                        onClick={() => {
                          patch({ includeNoteId: note.id, includeNoteTitle: note.title });
                          setNotePickerOpen(false);
                          setNoteQuery("");
                        }}
                      >
                        {note.title}
                      </button>
                    </li>
                  ))
                ) : (
                  <li className="px-1 py-1 text-[11px] text-muted-foreground">No notes match.</li>
                )}
              </ul>
            </div>
          ) : null}
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
          <input
            ref={imageInputRef}
            type="file"
            className="sr-only"
            accept={LARRY_IMAGE_ACCEPT}
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
            disabled={!enabled || locked || uploadingFiles || (pane.pendingAttachments ?? []).length >= LARRY_ATTACH_MAX_FILES}
            aria-label="Upload image"
            title="Upload a photo (jpg, png, webp, gif)"
            onClick={() => imageInputRef.current?.click()}
          >
            <ImageIcon className="size-4" />
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
            <JuniorMicButton
              enabled={enabled && !busy && !uploadingFiles}
              locked={locked}
              registerAbort={(abort) => {
                micAbortRef.current = abort;
              }}
              onPhaseChange={setSttPhase}
              onVoiceSubmit={submitVoiceTranscript}
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
                sttBusy ||
                (!draftNow().trim() && !(pane.pendingAttachments ?? []).length)
              }
              aria-label="Send"
            >
              <Send className="size-4" />
            </Button>
          )}
        </div>
        {sttPhase === "listening" ? (
          <p className="text-[11px] text-muted-foreground" role="status">
            {MIC_LIVE}
          </p>
        ) : sttPhase === "transcribing" ? (
          <p className="text-[11px] text-muted-foreground" role="status">
            {MIC_TRANSCRIBING}
          </p>
        ) : null}
        {(busy || aborting) && inFlightSpend ? (
          <p className="text-[11px] text-muted-foreground" data-junior-spend="" data-junior-route="">
            {inFlightSpend}
          </p>
        ) : null}
        {dragOver ? (
          <p className="text-[10px] text-muted-foreground">Drop files here — PDF, Word (.docx), text, or an image, up to 10 MB.</p>
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
