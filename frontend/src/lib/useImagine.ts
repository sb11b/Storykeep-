"use client";

import { toast } from "sonner";
import { ApiError, api } from "@/lib/api";

type ImagineFile = {
  kind?: string;
  media_id?: string;
};

type ImagineLine = {
  id: string;
  role: string;
  content: string;
  files?: ImagineFile[] | null;
};

type ImaginePane = {
  pendingAttachments?: Array<{ kind: string; id: string }> | null;
  conversationId: string | null;
  messages: ImagineLine[];
  draft: string;
  streamStatus?: string | null;
};

type UseImagineOptions = {
  pane: ImaginePane;
  onUpdate: (updater: (current: ImaginePane) => any) => void;
  onHistoryChanged?: () => void;
  draftNow: () => string;
  busy: boolean;
  aborting: boolean;
  enabled: boolean;
  locked: boolean;
  abortingRef: { current: boolean };
  inFlightRef: { current: boolean };
  abortRef: { current: AbortController | null };
  setBusy: (busy: boolean) => void;
  setAborting: (aborting: boolean) => void;
  applyStreamStatus: (kind: "working") => void;
  clearStreamStatus: () => void;
  hasMediaImage: (content: string | null | undefined) => boolean;
  toastErrorFromUnknown: (error: unknown, fallback: string) => void;
};

export function useImagine({
  pane,
  onUpdate,
  onHistoryChanged,
  draftNow,
  busy,
  aborting,
  enabled,
  locked,
  abortingRef,
  inFlightRef,
  abortRef,
  setBusy,
  setAborting,
  applyStreamStatus,
  clearStreamStatus,
  hasMediaImage,
  toastErrorFromUnknown,
}: UseImagineOptions) {
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

  return { imagine };
}
