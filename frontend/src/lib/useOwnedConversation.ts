"use client";

import { ApiError, api } from "@/lib/api";

type OwnedPane = {
  conversationId: string | null;
  createNonce: string | null;
  modelChoice: string;
  reasoningEffort: string;
};

type UseOwnedConversationOptions = {
  pane: OwnedPane;
  onUpdate: (updater: (current: OwnedPane) => any) => void;
  createNonceRef: { current: string | null };
  createInFlightRef: { current: Promise<string> | null };
  conversationIdForRequest: (value: string | null | undefined) => string | null;
  INVALID_CHAT_TOAST: string;
};

export function useOwnedConversation({
  pane,
  onUpdate,
  createNonceRef,
  createInFlightRef,
  conversationIdForRequest,
  INVALID_CHAT_TOAST,
}: UseOwnedConversationOptions) {
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

  return { ensureOwnedConversation };
}
