"use client";

import { toast } from "sonner";
import { ApiError, api } from "@/lib/api";

type ImagineFile = {
  kind?: string;
  media_id?: string;
};

type ImagineLine = {
  id: string;
  role?: string;
  content?: string;
  files?: ImagineFile[] | null;
  waiting?: boolean;
  failed?: boolean;
  error?: string | null;
  routeLabel?: string | null;
};

type ImaginePane = {
  conversationId: string | null;
  messages: ImagineLine[];
  streamStatus?: string | null;
  lastResolvedModel?: string | null;
  lastResolvedReasoning?: string | null;
};

type UseImagineChatOptions<T extends ImaginePane> = {
  pane: T;
  onUpdate: (updater: (current: T) => T) => void;
  onHistoryChanged?: () => void;
  label: string;
  applyStreamStatus: (kind: "generating") => void;
  abortRef: { current: AbortController | null };
  abortingRef: { current: boolean };
  setAborting: (aborting: boolean) => void;
  setBusy: (busy: boolean) => void;
  setInFlightSpend: (spend: string | null) => void;
  clearStreamStatus: () => void;
  spendChipLabel: (model?: string | null, reasoning?: string | null) => string;
  hasMediaImage: (content: string | null | undefined) => boolean;
  formatChatError: (status: number, detail: string, assistantName?: string) => string;
};

export function useImagineChat<T extends ImaginePane>({
  pane,
  onUpdate,
  onHistoryChanged,
  label,
  applyStreamStatus,
  abortRef,
  abortingRef,
  setAborting,
  setBusy,
  setInFlightSpend,
  clearStreamStatus,
  spendChipLabel,
  hasMediaImage,
  formatChatError,
}: UseImagineChatOptions<T>) {
  async function runImagineFromChat(options: {
    prompt: string;
    mediaIds: string[];
    userLine: T["messages"][number];
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
            } as T["messages"][number];
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
            } as T["messages"][number];
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

  return { runImagineFromChat };
}
