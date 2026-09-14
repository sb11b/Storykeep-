"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Image as ImageIcon, LoaderCircle, Mic, Paperclip, Pencil, Save, Send, Sparkles, Square, X } from "lucide-react";
import { GrokRowMenu } from "@/components/grok-row-menu";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { useDictation } from "@/components/dictation";
import { DestinationSelect, FolderSelect } from "@/components/destination-controls";
import { GrokChatMessage, type AddToNotesPayload } from "@/components/grok-chat-message";
import { GrokListenBar, useGrokMessageListen } from "@/components/grok-message-listen";
import { logReplyText, readReplyText } from "@/lib/grok-reply-speech";
import { wordIndexFromSelection } from "@/lib/tts-words";
import { DEFAULT_PANE_NAME, defaultGrokPaneName, chatStatusLine, type ChatStatusKind } from "@/lib/grok-pane-name";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { destinationLabel, type CustomNoteShelf, type FilingDestination } from "@/lib/custom-note-shelves";
import { folderById } from "@/lib/folders";
import { formatChatError, chatTimeoutToast, withAssistantName } from "@/lib/grok-chat-error";
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
import { chatContextOverCap, GROK_CONTEXT_TOAST } from "@/lib/grok-context";
import {
  articleNeedsIncludeSlice,
  parseSections,
  readerIncludeContext,
  resolveIncludeSlice,
  type IncludeMode,
} from "@/lib/include-chunk";
import { saveableThreadTurns, threadNoteMarkdown, threadNoteTitle } from "@/lib/junior-thread-note";
import { grokModelLabel, GROK_REASONING_EFFORTS, isGrokReasoningEffort, spendChipLabel } from "@/lib/grok-model";
import { hasMediaImage, imageToolIntent, MEDIA_MARKDOWN, thisTurnImageMediaIds } from "@/lib/chat-image";
import { readStoredTtsSpeed, readStoredTtsVoice, TTS_SPEEDS, writeStoredTtsSpeed, writeStoredTtsVoice } from "@/lib/tts-preferences";
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
  routeLabel?: string | null;
  includeChip?: string | null;
  includeHasMore?: boolean;
  includeNextOffset?: number | null;
  includeNextHeading?: string | null;
};

export type GrokPaneState = {
  id: string;
  displayName: string;
  conversationId: string | null;
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
  return {
    id: crypto.randomUUID(),
    displayName: defaultGrokPaneName(paneIndex),
    conversationId: null,
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
    noteDest: "notes",
    noteFolderId: null,
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
  panelOpen = true,
  ttsVoices = [],
  renamingLabel = false,
  renameDraft = "",
  onStartRename,
  onRenameDraftChange,
  onCommitRename,
  onCancelRename,
  customShelves = [],
  onCreateNoteShelf,
  onOpenArticle,
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
  onFocus: () => void;
  onUpdate: (updater: (pane: GrokPaneState) => GrokPaneState) => void;
  onRemove?: () => void;
  onSavedNote: (noteId?: string, destination?: FilingDestination, folderId?: string | null) => Promise<void>;
  onActivateListen: (stop: (() => void) | null) => void;
  onStopArticleListen?: () => void;
  onHistoryChanged?: () => void;
  panelOpen?: boolean;
  ttsVoices?: TtsVoice[];
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const draftRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const stopRef = useRef<() => void>(() => {});
  const abortRef = useRef<AbortController | null>(null);
  const abortingRef = useRef(false);
  const inFlightRef = useRef(false);
  const dictation = useDictation();
  const [busy, setBusy] = useState(false);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [voiceId, setVoiceId] = useState(() => readStoredTtsVoice());
  const [playbackSpeed, setPlaybackSpeed] = useState(() => readStoredTtsSpeed());
  const [listenTarget, setListenTarget] = useState<ListenTarget | null>(null);
  const [activeWord, setActiveWord] = useState<number | null>(null);
  const [uploadingFiles, setUploadingFiles] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [streamStatus, setStreamStatus] = useState<ChatStatusKind | null>(null);
  const [aborting, setAborting] = useState(false);
  const [inFlightSpend, setInFlightSpend] = useState<string | null>(null);
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
      if (kind === "writing" || kind === "generating" || kind == null) {
        if (thinkingTimerRef.current != null) {
          window.clearTimeout(thinkingTimerRef.current);
          thinkingTimerRef.current = null;
        }
      }
      generatingRef.current = kind === "generating";
      if (kind === "working") gotDeltaRef.current = false;
      if (kind === "writing") gotDeltaRef.current = true;
      setStreamStatus(kind);
      onUpdate((current) => (current.streamStatus === kind ? current : { ...current, streamStatus: kind }));
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

  const stopGeneration = useCallback(() => {
    dictation?.abort();
    abortingRef.current = true;
    setAborting(true);
    abortRef.current?.abort();
    setBusy(false);
    clearStreamStatus();
    onUpdate((current) => ({
      ...current,
      streamStatus: null,
      messages: current.messages.map((item) => (item.waiting ? { ...item, waiting: false } : item)),
    }));
  }, [clearStreamStatus, dictation, onUpdate]);

  const beginStreamStatus = useCallback(() => {
    if (thinkingTimerRef.current != null) window.clearTimeout(thinkingTimerRef.current);
    gotDeltaRef.current = false;
    applyStreamStatus("working");
    thinkingTimerRef.current = window.setTimeout(() => {
      if (!gotDeltaRef.current) applyStreamStatus("thinking");
    }, 250);
  }, [applyStreamStatus]);

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
        const local = readStoredTtsVoice(ttsVoices[0]!.voice_id);
        const pick = [saved, local].find((item) => item && ttsVoices.some((voice) => voice.voice_id === item));
        const next = pick || ttsVoices[0]!.voice_id;
        setVoiceId(next);
        writeStoredTtsVoice(next);
      })
      .catch(() => {
        if (cancelled) return;
        const stored = readStoredTtsVoice(ttsVoices[0]!.voice_id);
        if (ttsVoices.some((voice) => voice.voice_id === stored)) setVoiceId(stored);
        else setVoiceId(ttsVoices[0]!.voice_id);
      });
    return () => {
      cancelled = true;
    };
  }, [ttsVoices]);

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
      if (abortRef.current || busy) {
        event.preventDefault();
        stopGeneration();
      }
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [busy, dictation, stopGeneration]);

  useEffect(() => {
    const el = draftRef.current;
    if (el) dictation?.attach(el);
  }, [dictation, pane.draft]);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight });
  }, [pane.messages]);

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
  }) {
    const { message, retry = false, userLine, assistantId } = options;
    const controller = new AbortController();
    abortRef.current = controller;
    abortingRef.current = false;
    setAborting(false);
    setInFlightSpend(null);

    setBusy(true);
    try {
      await api.streamChat(
        {
          message,
          retry,
          conversation_id: pane.conversationId,
          model: pane.modelChoice,
          reasoning_effort: pane.modelChoice === "auto" ? "auto" : pane.reasoningEffort,
          article_id: articleId,
          include_article: Boolean(pane.includeArticle && articleId),
          include_note_id: pane.includeNoteId || undefined,
          include_mode: options.includeMode || pane.includeMode,
          include_selection: options.includeSelection || undefined,
          include_heading: options.includeHeading || pane.includeHeading || undefined,
          include_offset: options.includeOffset ?? pane.includeOffset ?? 0,
          recap_question: pane.recapQuestion,
          media_ids: retry ? undefined : options.mediaIds,
        },
        (delta) => {
          const generating = generatingRef.current;
          if (!generating) markWriting();
          onUpdate((current) => ({
            ...current,
            streamStatus: generating ? "generating" : "writing",
            messages: current.messages.map((item) =>
              item.id === assistantId
                ? {
                    ...item,
                    waiting: false,
                    content: MEDIA_MARKDOWN.test(delta) ? delta : item.content + delta,
                    failed: false,
                    error: null,
                  }
                : item,
            ),
          }));
        },
        (meta) => {
          if (meta.stream_status === "generating") {
            applyStreamStatus("generating");
          } else if (!gotDeltaRef.current) {
            applyStreamStatus("thinking");
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
                        waiting: false,
                        id: meta.assistant_message_id!,
                        failed: meta.partial ? item.failed : false,
                        error: meta.partial ? item.error : null,
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
              const spend = spendChipLabel(
                meta.model || next.lastResolvedModel,
                meta.reasoning_effort || next.lastResolvedReasoning,
              );
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
          beginStreamStatus();
        },
      );
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
      const detail = error instanceof ApiError ? error.message : `${label} did not reply`;
      const formatted = detail.startsWith("Chat failed (HTTP")
        ? withAssistantName(detail, label)
        : formatChatError(status, detail, label);
      const timeoutToast = chatTimeoutToast(status, formatted);
      onUpdate((current) => ({
        ...current,
        streamStatus: null,
        messages: current.messages.map((item) =>
          item.id === assistantId
            ? {
                ...item,
                waiting: false,
                failed: true,
                error: formatted,
                // Keep streamed words; drop fake Imagine captions with no media id.
                content:
                  hasMediaImage(item.content) || /\/api\/v1\/media\//.test(item.content)
                    ? item.content
                    : /Generating the image|Here's the image/i.test(item.content)
                      ? ""
                      : item.content,
              }
            : item,
        ),
      }));
      toast.error(timeoutToast || formatted);
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      abortingRef.current = false;
      setAborting(false);
      setBusy(false);
      clearStreamStatus();
      onUpdate((current) => ({
        ...current,
        messages: current.messages.map((item) =>
          item.id === assistantId && item.waiting ? { ...item, waiting: false } : item,
        ),
      }));
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

  function contextTooLarge(draft: string, extraMessages: ChatLine[] = pane.messages) {
    const noteBody =
      pane.includeNoteId && articleId && pane.includeNoteId === articleId ? articleBody : null;
    const slice = plannedIncludeSlice();
    return chatContextOverCap({
      messages: extraMessages,
      draft,
      includeArticle: Boolean(pane.includeArticle && articleId),
      articleBody,
      includeNote: Boolean(pane.includeNoteId),
      noteBody,
      includeSliceChars: slice?.chars,
      pendingExtracts: (pane.pendingAttachments ?? []).map((item) => item.extract_text),
    });
  }

  async function send(opts?: {
    message?: string;
    includeMode?: IncludeMode;
    includeHeading?: string | null;
    includeSelection?: string | null;
    includeOffset?: number;
  }) {
    const content = (opts?.message ?? pane.draft).trim();
    const pending = pane.pendingAttachments ?? [];
    if (pending.some((item) => !item.id)) {
      toast.error("Wait for the file to finish uploading.");
      return;
    }
    const files = pending.filter((item) => item.id);
    if ((!content && !files.length) || busy || aborting || abortingRef.current || !enabled || inFlightRef.current) {
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
      toast.error(GROK_CONTEXT_TOAST);
      return;
    }
    dictation?.abort();
    inFlightRef.current = true;
    try {
    const imageIds = thisTurnImageMediaIds(files);
    const intent = imageToolIntent(content, imageIds.length > 0);
    const wantsImage = intent === "edit" || intent === "generate";
    const includeMode = opts?.includeMode || pane.includeMode;
    const includeHeading = opts?.includeHeading ?? pane.includeHeading;
    const includeSelection = opts?.includeSelection || (includeMode === "selection" ? readerCtx.selection : undefined);
    const includeOffset = opts?.includeOffset ?? pane.includeOffset ?? 0;
    const previewSlice =
      pane.includeArticle && articleId
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
    };
    const assistantId = crypto.randomUUID();
    onUpdate((current) => ({
      ...current,
      draft: "",
      pendingAttachments: [],
      streamStatus: wantsImage ? "generating" : "working",
      messages: [
        ...current.messages,
        userLine,
        { id: assistantId, role: "assistant", content: "", waiting: true },
      ],
    }));
    setStreamStatus(wantsImage ? "generating" : "working");
    if (intent === "edit" && imageIds.length) {
      await runImagineFromChat({
        prompt: content,
        mediaIds: imageIds,
        userLine,
        assistantId,
      });
      return;
    }
    if (intent === "generate") {
      await runImagineFromChat({
        prompt: content,
        mediaIds: imageIds,
        userLine,
        assistantId,
      });
      return;
    }
    await runStream({
      message: content || (files[0] ? `Please look at ${files.map((item) => item.name).join(", ")}.` : ""),
      userLine,
      assistantId,
      mediaIds: files.map((item) => item.id),
      includeMode,
      includeHeading,
      includeSelection,
      includeOffset,
    });
    } finally {
      inFlightRef.current = false;
    }
  }

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
              content: result.user_message.content,
              files: result.user_message.files,
            };
          }
          if (item.id === assistantId) {
            return {
              id: result.assistant_message.id,
              role: "assistant" as const,
              content: result.assistant_message.content,
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
    const prompt = pane.draft.trim();
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
            content: result.user_message.content,
            files: result.user_message.files,
          },
          {
            id: result.assistant_message.id,
            role: "assistant",
            content: result.assistant_message.content,
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
      toast.error(GROK_CONTEXT_TOAST);
      return;
    }
    inFlightRef.current = true;
    try {
    const retryImages = thisTurnImageMediaIds(userLine.files);
    const retryIntent = imageToolIntent(userLine.content, retryImages.length > 0);
    const retryWantsImage = retryIntent === "generate" || (retryIntent === "edit" && retryImages.length > 0);
    onUpdate((current) => ({
      ...current,
      streamStatus: retryWantsImage ? "generating" : "working",
      messages: current.messages.map((item) =>
        item.id === assistantId
          ? { ...item, content: "", failed: false, error: null, waiting: true }
          : item,
      ),
    }));
    setStreamStatus(retryWantsImage ? "generating" : "working");
    if (retryWantsImage) {
      await runImagineFromChat({
        prompt: userLine.content,
        mediaIds: retryImages,
        userLine,
        assistantId,
      });
      return;
    }
    await runStream({
      message: userLine.content,
      retry: true,
      userLine,
      assistantId,
    });
    } finally {
      inFlightRef.current = false;
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
          { id: result.user_message.id, role: "user", content: result.user_message.content },
          {
            id: result.assistant_message.id,
            role: "assistant",
            content: result.assistant_message.content,
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
    const dest = payload.dest;
    const folderId = payload.folderId;
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
      const folderName = folderById(folders, folderId)?.name;
      toast.success(
        folderName
          ? `Saved to StoryKeep/${destinationLabel(dest, customShelves)}/${folderName}.`
          : `Saved to StoryKeep/${destinationLabel(dest, customShelves)}.`,
      );
      await onSavedNote(article.id, dest, folderId);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not save that note");
    }
  }

  async function saveChat() {
    if (savingChat) return;
    const dest = (pane.noteDest || "").trim();
    if (!dest) {
      toast.error("Pick a shelf before saving this chat.");
      document.getElementById(shelfSelectId)?.focus();
      return;
    }
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
            pane.noteFolderId,
          );
          updated = true;
        } catch (error) {
          if (!(error instanceof ApiError && error.status === 404)) {
            throw error;
          }
        }
      }
      if (!article) {
        article = await api.composeVaultNote(title, markdown, ["grok"], dest, false, pane.noteFolderId);
      }
      patch({ savedNoteId: article.id, conversationTitle: title });
      if (pane.conversationId && persist) {
        try {
          await api.patchChatConversation(pane.conversationId, { saved_note_id: article.id });
        } catch {
          /* note is saved; linking it to the thread is best-effort */
        }
      }
      const folderName = folderById(folders, pane.noteFolderId)?.name;
      const where = folderName
        ? `${destinationLabel(dest, customShelves)} / ${folderName}`
        : destinationLabel(dest, customShelves);
      toast.success(updated ? `Updated “${title}” on ${where}.` : `Saved “${title}” to ${where}.`);
      await onSavedNote(article.id, dest, pane.noteFolderId);
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
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not create folder");
    }
  }

  function handleNoteDestChange(next: FilingDestination | "") {
    if (!next) return;
    patch({ noteDest: next, noteFolderId: null });
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
  const voiceOptions = ttsVoices.length ? ttsVoices : [{ voice_id: "eve", name: "Eve" }];
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
          onChange={(next) => patch({ noteFolderId: next })}
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

      {visibleStatus ? (
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
              {pane.includeArticle && articleId
                ? "Ask about this article or school coding."
                : "Ask for school coding help — explanations, debugging, or fenced code."}
            </p>
          ) : (
            pane.messages.map((item) => (
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
                onRememberFiling={(dest, folderId) => patch({ noteDest: dest, noteFolderId: folderId })}
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
                        { id: message.id, role: "assistant", content: message.content, files: message.files },
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
                  item.role === "assistant" &&
                  visibleStatus &&
                  (item.waiting || (visibleStatus === "writing" && item.id === lastAssistantId))
                    ? chatStatusLine(label, visibleStatus)
                    : null
                }
                onRegisterBody={registerBody}
                onListen={requestListen}
                onTtsWordPick={(messageId, index) => {
                  clickedWordRef.current = { messageId, index };
                }}
                onAddToNotes={(payload) => void addToNotes(payload, item.id)}
                onRetry={item.role === "assistant" && item.failed ? () => void retryAssistant(item.id) : undefined}
                onRunSnippet={(messageId, code) => void runSnippet(messageId, code)}
                onOpenArticle={onOpenArticle}
              />
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
        <div className="flex gap-2">
          <Textarea
            ref={draftRef}
            dictate={false}
            className="min-h-12 max-h-28 flex-1 resize-y rounded-md border bg-background px-2 py-1.5 text-sm"
            value={pane.draft}
            onChange={(event) => patch({ draft: event.target.value })}
            placeholder={
              pane.includeArticle && articleId
                ? "Ask about this article or school coding…"
                : `Ask ${label} for school coding help…`
            }
            disabled={!enabled}
            onFocus={() => {
              onFocus();
              if (draftRef.current) dictation?.attach(draftRef.current);
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
            className="relative z-10 size-9 shrink-0 self-end"
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
            className="relative z-10 size-9 shrink-0 self-end"
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
            className="relative z-10 size-9 shrink-0 self-end"
            disabled={!enabled || locked || busy || uploadingFiles}
            aria-label="Imagine"
            title="Imagine — generate an image from this prompt"
            onClick={() => void imagine()}
          >
            <Sparkles className="size-4" />
          </Button>
          {sttEnabled && !locked ? (
            <div className="flex shrink-0 flex-col gap-1">
              <Button
                type="button"
                size="icon"
                variant={dictation?.listening ? "destructive" : "outline"}
                className="size-9"
                aria-label={dictation?.listening ? "Stop dictation" : "Tap to talk"}
                title={
                  dictation?.continuous
                    ? "Tap to talk (continuous until Stop)"
                    : "Tap to talk (one utterance)"
                }
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  const el = draftRef.current;
                  if (!el) return;
                  dictation?.startFor(el);
                }}
              >
                <Mic className="size-4" />
              </Button>
              <Button
                type="button"
                size="icon"
                variant={dictation?.continuous ? "default" : "outline"}
                className="size-9"
                aria-pressed={Boolean(dictation?.continuous)}
                aria-label={dictation?.continuous ? "Continuous dictation on" : "Continuous dictation off"}
                title={
                  dictation?.continuous
                    ? "Continuous on — keep listening across pauses until Stop"
                    : "Continuous off — one utterance then stop"
                }
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => dictation?.setContinuous(!dictation.continuous)}
              >
                <span className="text-[9px] font-semibold leading-none">Cont</span>
              </Button>
            </div>
          ) : null}
          {busy || aborting ? (
            <Button
              type="button"
              size="icon"
              variant="destructive"
              className="size-9 shrink-0 self-end"
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
              className="size-9 shrink-0 self-end"
              disabled={!enabled || aborting || (!pane.draft.trim() && !(pane.pendingAttachments ?? []).length)}
              aria-label="Send"
            >
              <Send className="size-4" />
            </Button>
          )}
        </div>
        {(busy || aborting) && inFlightSpend ? (
          <p className="text-[11px] text-muted-foreground" data-junior-spend="" data-junior-route="">
            {inFlightSpend}
          </p>
        ) : null}
        {dictation?.listening && sttEnabled && !locked ? (
          <p className="text-[10px] text-muted-foreground">
            {dictation.continuous || dictation.sessionContinuous
              ? "Listening — continuous on this box until Stop."
              : "Listening — one utterance…"}
          </p>
        ) : dictation?.idleHint && sttEnabled && !locked ? (
          <p className="text-[10px] text-muted-foreground" role="status">
            {dictation.idleHint}
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
