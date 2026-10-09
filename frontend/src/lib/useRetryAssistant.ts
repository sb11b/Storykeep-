"use client";

import { toast } from "sonner";

type RetryFile = { id?: string; media_id?: string; kind?: string };

type RetryMessage = {
  id: string;
  role: string;
  content: string;
  files?: RetryFile[] | null;
  failed?: boolean;
  error?: string | null;
  waiting?: boolean;
  turnStatus?: string | null;
};

type RetryPane = {
  conversationId: string | null;
  messages: RetryMessage[];
  streamStatus?: string | null;
};

type UseRetryAssistantOptions<TPane extends RetryPane, TContext> = {
  pane: TPane;
  onUpdate: (updater: (current: TPane) => TPane) => void;
  busy: boolean;
  aborting: boolean;
  abortingRef: { current: boolean };
  enabled: boolean;
  inFlightRef: { current: boolean };
  turnIdRef: { current: number };
  abortRef: { current: AbortController | null };
  setAborting: (aborting: boolean) => void;
  setBusy: (busy: boolean) => void;
  setStreamStatus: (status: "generating" | "queued") => void;
  contextTooLarge: (draft: string) => boolean;
  threadContextToast: (input: TContext) => string;
  contextInput: (draft: string) => TContext;
  thisTurnImageMediaIds: (files: RetryFile[] | null | undefined) => string[];
  imageToolIntent: (text: string, hasImage: boolean) => string | null;
  runStream: (options: {
    message: string;
    retry: boolean;
    userLine: TPane["messages"][number];
    assistantId: string;
    controller: AbortController;
    turnId: number;
  }) => Promise<void> | void;
};

export function useRetryAssistant<TPane extends RetryPane, TContext>({
  pane,
  onUpdate,
  busy,
  aborting,
  abortingRef,
  enabled,
  inFlightRef,
  turnIdRef,
  abortRef,
  setAborting,
  setBusy,
  setStreamStatus,
  contextTooLarge,
  threadContextToast,
  contextInput,
  thisTurnImageMediaIds,
  imageToolIntent,
  runStream,
}: UseRetryAssistantOptions<TPane, TContext>) {
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

  return { retryAssistant };
}
