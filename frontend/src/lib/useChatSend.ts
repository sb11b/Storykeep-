"use client";

import { useRef } from "react";

type IncludeMode = "auto" | "selection" | "heading" | "chunk";

type PendingFile = {
  id: string;
  name: string;
  size: number;
  url: string;
  kind: "image" | "file";
  content_type: string;
  extract_text?: string | null;
};

type MessageFile = {
  media_id: string;
  filename: string;
  content_type: string;
  kind: "image" | "file";
  url: string;
  byte_size?: number | null;
  extract_text?: string | null;
};

type SendMessage = {
  id: string;
  role: string;
  content: string;
  waiting?: boolean;
  turnStatus?: string | null;
};

type SendPane = {
  pendingAttachments?: PendingFile[] | null;
  includeArticle: boolean;
  includeMode: IncludeMode;
  includeHeading: string | null;
  includeOffset: number;
  workingNoteId: string | null;
  workingNoteTitle: string | null;
  messages: SendMessage[];
  draft: string;
  streamStatus?: string | null;
};

type SendOpts = {
  message?: string;
  fromStt?: boolean;
  keepDraft?: string;
  skipPasteSplit?: boolean;
  includeMode?: IncludeMode;
  includeHeading?: string | null;
  includeSelection?: string | null;
  includeOffset?: number;
};

type UseChatSendOptions<T extends SendPane, TContext> = {
  pane: T;
  onUpdate: (updater: (current: T) => T) => void;
  enabled: boolean;
  busy: boolean;
  aborting: boolean;
  abortingRef: { current: boolean };
  inFlightRef: { current: boolean };
  setAborting: (aborting: boolean) => void;
  setBusy: (busy: boolean) => void;
  setStreamStatus: (status: "generating" | "queued") => void;
  turnIdRef: { current: number };
  abortRef: { current: AbortController | null };
  toast: { error: (message: string) => void };
  dictation: { abort: () => void } | null;
  voice: { micAbortRef: { readonly current: (() => void) | null } };
  readerCtx: { selection: string };
  articleId: string | null;
  articleTitle: string | null;
  articleBody?: string | null;
  contextTooLarge: (draft: string) => boolean;
  threadContextToast: (input: TContext) => string;
  contextInput: (draft: string) => TContext;
  offerPasteSplit: (draft: string) => void;
  thisTurnImageMediaIds: (files: PendingFile[]) => string[];
  imageToolIntent: (text: string, hasImage: boolean) => string | null;
  headingFromInstruction: (message: string, body: string) => string | null;
  resolveIncludeSlice: (input: {
    body: string;
    mode?: IncludeMode | null;
    selection?: string | null;
    heading?: string | null;
    offset?: number;
    title?: string | null;
    cap?: number;
    hardMax?: number;
  }) => { chip?: string | null } | null;
  articleNeedsIncludeSlice: (body: string | null | undefined, cap?: number) => boolean;
  pendingToMessageFile: (item: PendingFile) => MessageFile;
  runStream: (options: {
    message: string;
    userLine: {
      id: string;
      role: "user";
      content: string;
      files: MessageFile[];
      includeChip?: string | null;
      includeMode: IncludeMode;
      includeHeading: string | null;
      includeOffset: number;
    };
    assistantId: string;
    mediaIds: string[];
    includeMode: IncludeMode;
    includeHeading: string | null;
    includeSelection?: string | null;
    includeOffset: number;
    controller: AbortController;
    turnId: number;
  }) => Promise<void> | void;
  draftNow: () => string;
  PASTE_FIRST_CHUNK_CHARS: number;
  WORKING_NOTE_CHAR_CAP: number;
};

export function useChatSend<T extends SendPane, TContext>({
  pane,
  onUpdate,
  enabled,
  busy,
  aborting,
  abortingRef,
  inFlightRef,
  setAborting,
  setBusy,
  setStreamStatus,
  turnIdRef,
  abortRef,
  toast,
  dictation,
  voice,
  readerCtx,
  articleId,
  articleTitle,
  articleBody,
  contextTooLarge,
  threadContextToast,
  contextInput,
  offerPasteSplit,
  thisTurnImageMediaIds,
  imageToolIntent,
  headingFromInstruction,
  resolveIncludeSlice,
  articleNeedsIncludeSlice,
  pendingToMessageFile,
  runStream,
  draftNow,
  PASTE_FIRST_CHUNK_CHARS,
  WORKING_NOTE_CHAR_CAP,
}: UseChatSendOptions<T, TContext>) {
  const sendRef = useRef<(opts?: SendOpts) => Promise<void>>(async () => {});

  async function send(opts?: SendOpts) {
    if (!opts?.fromStt) {
      dictation?.abort();
      voice.micAbortRef.current?.();
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
      const userLine = {
        id: crypto.randomUUID(),
        role: "user" as const,
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
          userLine as T["messages"][number],
          {
            id: assistantId,
            role: "assistant" as const,
            content: "",
            waiting: true,
            turnStatus: wantsImage ? "writing" : "queued",
          } as T["messages"][number],
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
  return { send, sendRef };
}
